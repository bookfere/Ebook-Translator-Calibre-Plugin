from datetime import datetime, timezone
from datetime import timedelta
import json
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from common.artifacts import SQLITE_CONTENT_TYPE, build_job_sqlite_key

from ..auth import AuthContext, get_auth_context
from ..config import Settings, get_settings
from ..db import get_connection
from ..models import (
    ArtifactUrlResponse,
    CancelJobResponse,
    CreateJobRequest,
    CreateJobResponse,
    DownloadUrlResponse,
    JobListResponse,
    JobResponse,
    RebuildJobResponse,
    JobStatus,
)
from ..queue import QueuePublisher, get_queue_publisher
from ..r2 import R2Client, R2ObjectNotFound, get_r2_client

router = APIRouter(prefix="/v1", tags=["jobs"])

TERMINAL_STATUSES = {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value, JobStatus.CANCELED.value, JobStatus.EXPIRED.value}


def _build_input_key(user_id: str, job_id: UUID, input_format: str) -> str:
    return f"raw/{user_id}/{job_id}/input.{input_format.lower()}"


def _build_output_key(user_id: str, job_id: UUID, output_format: str) -> str:
    return f"result/{user_id}/{job_id}/output.{output_format.lower()}"


def _normalize_job(row: asyncpg.Record) -> JobResponse:
    return JobResponse(
        job_id=row["id"],
        status=JobStatus(row["status"]),
        progress=row["progress"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        input_key=row["input_key"],
        output_key=row["output_key"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        expires_at=row["expires_at"],
    )


async def _get_job_for_user(conn: asyncpg.Connection, job_id: UUID, auth: AuthContext) -> asyncpg.Record | None:
    if auth.is_admin:
        return await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)
    return await conn.fetchrow("SELECT * FROM jobs WHERE id = $1 AND user_id = $2", job_id, auth.user_id)


def _ensure_job_not_expired(row: asyncpg.Record) -> None:
    if row["status"] == JobStatus.EXPIRED.value or row["expires_at"] <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Job artifacts have expired")


def _ensure_job_terminal(row: asyncpg.Record) -> None:
    if row["status"] not in TERMINAL_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job is still in progress")


@router.post("/jobs", response_model=CreateJobResponse)
async def create_job(
    request: CreateJobRequest,
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
    conn: asyncpg.Connection = Depends(get_connection),
    queue: QueuePublisher = Depends(get_queue_publisher),
    r2: R2Client = Depends(get_r2_client),
) -> CreateJobResponse:
    input_format = request.input_format.lower()
    output_format = request.output_format.lower()
    engine = request.engine.lower()
    source_lang = request.source_lang.lower()
    target_lang = request.target_lang.lower()

    if input_format not in settings.allowed_input_formats:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported input format")
    if output_format not in settings.allowed_output_formats:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported output format")
    if engine not in settings.allowed_engines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported engine")
    if input_format in {"srt", "pgn"} and output_format != input_format:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SRT/PGN output format must match input format",
        )

    try:
        job_id = UUID(request.upload_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid upload_key") from exc

    input_key = _build_input_key(auth.user_id, job_id, input_format)
    output_key = _build_output_key(auth.user_id, job_id, output_format)

    try:
        metadata = r2.head_object(settings.r2_raw_bucket, input_key)
    except R2ObjectNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uploaded file not found") from exc

    if metadata.size > settings.max_upload_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file exceeds max size")

    expires_at_seconds = int(timedelta(hours=settings.object_ttl_hours).total_seconds())
    usage_today = await conn.fetchval(
        """
        SELECT jobs_created
        FROM usage_daily
        WHERE user_id = $1 AND usage_date = CURRENT_DATE
        """,
        auth.user_id,
    )
    if usage_today is not None and int(usage_today) >= settings.daily_jobs_limit_per_user:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily job quota exceeded",
        )

    async with conn.transaction():
        created = await conn.fetchrow(
            """
            INSERT INTO jobs (
                id, user_id, status, progress, input_key, output_key,
                input_format, output_format, source_lang, target_lang,
                engine, engine_options, content_type, input_size, expires_at
            ) VALUES (
                $1, $2, 'queued', 0, $3, $4,
                $5, $6, $7, $8,
                $9, $10::jsonb, $11, $12, NOW() + ($13::bigint * interval '1 second')
            )
            ON CONFLICT (id) DO NOTHING
            RETURNING id, status, created_at
            """,
            job_id,
            auth.user_id,
            input_key,
            output_key,
            input_format,
            output_format,
            source_lang,
            target_lang,
            engine,
            json.dumps(request.engine_options),
            metadata.content_type,
            metadata.size,
            expires_at_seconds,
        )

        if created is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job already exists")

        await conn.execute(
            """
            INSERT INTO job_events (job_id, user_id, event_type, message, details)
            VALUES ($1, $2, 'queued', 'Job queued', $3::jsonb)
            """,
            job_id,
            auth.user_id,
            json.dumps({"engine": engine, "input_format": input_format, "output_format": output_format}),
        )

        await conn.execute(
            """
            INSERT INTO usage_daily (user_id, usage_date, jobs_created, bytes_in, bytes_out)
            VALUES ($1, CURRENT_DATE, 1, $2, 0)
            ON CONFLICT (user_id, usage_date)
            DO UPDATE SET
                jobs_created = usage_daily.jobs_created + 1,
                bytes_in = usage_daily.bytes_in + EXCLUDED.bytes_in
            """,
            auth.user_id,
            metadata.size,
        )

    try:
        task_id = queue.enqueue_translation_job(str(job_id))
    except Exception as exc:  # noqa: BLE001
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE jobs
                SET status = 'failed',
                    error_code = 'QUEUE_ERROR',
                    error_message = $2,
                    finished_at = NOW()
                WHERE id = $1
                """,
                job_id,
                str(exc)[:1000],
            )
            await conn.execute(
                """
                INSERT INTO job_events (job_id, user_id, event_type, message, details)
                VALUES ($1, $2, 'failed', 'Queue publish failed', $3::jsonb)
                """,
                job_id,
                auth.user_id,
                json.dumps({"error": str(exc)[:500]}),
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue job",
        ) from exc

    await conn.execute(
        """
        INSERT INTO job_events (job_id, user_id, event_type, message, details)
        VALUES ($1, $2, 'enqueued', 'Job published to queue', $3::jsonb)
        """,
        job_id,
        auth.user_id,
        json.dumps({"task_id": task_id}),
    )

    return CreateJobResponse(job_id=created["id"], status=JobStatus(created["status"]), created_at=created["created_at"])


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    conn: asyncpg.Connection = Depends(get_connection),
) -> JobResponse:
    row = await _get_job_for_user(conn, job_id, auth)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _normalize_job(row)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(get_auth_context),
    conn: asyncpg.Connection = Depends(get_connection),
) -> JobListResponse:
    if auth.is_admin:
        rows = await conn.fetch(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit,
            offset,
        )
    else:
        rows = await conn.fetch(
            "SELECT * FROM jobs WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            auth.user_id,
            limit,
            offset,
        )

    return JobListResponse(items=[_normalize_job(row) for row in rows], limit=limit, offset=offset)


@router.post("/jobs/{job_id}:cancel", response_model=CancelJobResponse)
async def cancel_job(
    job_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    conn: asyncpg.Connection = Depends(get_connection),
) -> CancelJobResponse:
    row = await _get_job_for_user(conn, job_id, auth)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if row["status"] in TERMINAL_STATUSES:
        return CancelJobResponse(job_id=job_id, status=JobStatus(row["status"]))

    async with conn.transaction():
        updated = await conn.fetchrow(
            """
            UPDATE jobs
            SET status = 'canceled', canceled_at = NOW(), finished_at = NOW(), progress = LEAST(progress, 99)
            WHERE id = $1
            RETURNING status
            """,
            job_id,
        )
        await conn.execute(
            """
            INSERT INTO job_events (job_id, user_id, event_type, message, details)
            VALUES ($1, $2, 'canceled', 'Job canceled by user', '{}'::jsonb)
            """,
            job_id,
            auth.user_id,
        )

    return CancelJobResponse(job_id=job_id, status=JobStatus(updated["status"]))


@router.get("/jobs/{job_id}/sqlite-download-url", response_model=ArtifactUrlResponse)
async def get_sqlite_download_url(
    job_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
    conn: asyncpg.Connection = Depends(get_connection),
    r2: R2Client = Depends(get_r2_client),
) -> ArtifactUrlResponse:
    row = await _get_job_for_user(conn, job_id, auth)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    _ensure_job_terminal(row)
    _ensure_job_not_expired(row)

    sqlite_key = build_job_sqlite_key(str(row["user_id"]), str(job_id))
    try:
        r2.head_object(settings.r2_result_bucket, sqlite_key)
    except R2ObjectNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SQLite artifact not found") from exc

    return ArtifactUrlResponse(
        job_id=job_id,
        url=r2.presign_get(settings.r2_result_bucket, sqlite_key, settings.presigned_get_expires_seconds),
        expires_in_seconds=settings.presigned_get_expires_seconds,
    )


@router.post("/jobs/{job_id}/sqlite-upload-url", response_model=ArtifactUrlResponse)
async def get_sqlite_upload_url(
    job_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
    conn: asyncpg.Connection = Depends(get_connection),
    r2: R2Client = Depends(get_r2_client),
) -> ArtifactUrlResponse:
    row = await _get_job_for_user(conn, job_id, auth)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    _ensure_job_terminal(row)
    _ensure_job_not_expired(row)

    sqlite_key = build_job_sqlite_key(str(row["user_id"]), str(job_id))
    return ArtifactUrlResponse(
        job_id=job_id,
        url=r2.presign_put(
            settings.r2_result_bucket,
            sqlite_key,
            SQLITE_CONTENT_TYPE,
            settings.presigned_put_expires_seconds,
        ),
        expires_in_seconds=settings.presigned_put_expires_seconds,
    )


@router.post("/jobs/{job_id}:rebuild", response_model=RebuildJobResponse)
async def rebuild_job(
    job_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
    conn: asyncpg.Connection = Depends(get_connection),
    queue: QueuePublisher = Depends(get_queue_publisher),
    r2: R2Client = Depends(get_r2_client),
) -> RebuildJobResponse:
    row = await _get_job_for_user(conn, job_id, auth)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    _ensure_job_not_expired(row)

    if row["status"] not in {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value, JobStatus.CANCELED.value}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job cannot be rebuilt right now")

    sqlite_key = build_job_sqlite_key(str(row["user_id"]), str(job_id))
    try:
        r2.head_object(settings.r2_raw_bucket, row["input_key"])
        r2.head_object(settings.r2_result_bucket, sqlite_key)
    except R2ObjectNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Required rebuild artifact not found") from exc

    previous_state = {
        "status": row["status"],
        "progress": row["progress"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "canceled_at": row["canceled_at"],
        "error_code": row["error_code"],
        "error_message": row["error_message"],
    }

    async with conn.transaction():
        await conn.execute(
            """
            UPDATE jobs
            SET status = 'queued',
                progress = 0,
                started_at = NULL,
                finished_at = NULL,
                canceled_at = NULL,
                error_code = NULL,
                error_message = NULL
            WHERE id = $1
            """,
            job_id,
        )
        await conn.execute(
            """
            INSERT INTO job_events (job_id, user_id, event_type, message, details)
            VALUES ($1, $2, 'rebuild_queued', 'Job rebuild queued', '{}'::jsonb)
            """,
            job_id,
            auth.user_id,
        )

    try:
        task_id = queue.enqueue_rebuild_job(str(job_id))
    except Exception as exc:  # noqa: BLE001
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE jobs
                SET status = $2,
                    progress = $3,
                    started_at = $4,
                    finished_at = $5,
                    canceled_at = $6,
                    error_code = $7,
                    error_message = $8
                WHERE id = $1
                """,
                job_id,
                previous_state["status"],
                previous_state["progress"],
                previous_state["started_at"],
                previous_state["finished_at"],
                previous_state["canceled_at"],
                previous_state["error_code"],
                previous_state["error_message"],
            )
            await conn.execute(
                """
                INSERT INTO job_events (job_id, user_id, event_type, message, details)
                VALUES ($1, $2, 'rebuild_queue_failed', 'Rebuild queue publish failed', $3::jsonb)
                """,
                job_id,
                auth.user_id,
                json.dumps({"error": str(exc)[:500]}),
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue rebuild job",
        ) from exc

    await conn.execute(
        """
        INSERT INTO job_events (job_id, user_id, event_type, message, details)
        VALUES ($1, $2, 'rebuild_enqueued', 'Job rebuild published to queue', $3::jsonb)
        """,
        job_id,
        auth.user_id,
        json.dumps({"task_id": task_id}),
    )

    return RebuildJobResponse(job_id=job_id, status=JobStatus.QUEUED)


@router.get("/jobs/{job_id}/download-url", response_model=DownloadUrlResponse)
async def get_download_url(
    job_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
    conn: asyncpg.Connection = Depends(get_connection),
    r2: R2Client = Depends(get_r2_client),
) -> DownloadUrlResponse:
    row = await _get_job_for_user(conn, job_id, auth)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if row["status"] != JobStatus.SUCCEEDED.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job is not completed")
    _ensure_job_not_expired(row)
    if row["output_key"] is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Output object not available")

    url = r2.presign_get(
        settings.r2_result_bucket,
        row["output_key"],
        settings.presigned_get_expires_seconds,
    )
    return DownloadUrlResponse(
        job_id=job_id,
        download_url=url,
        expires_in_seconds=settings.presigned_get_expires_seconds,
    )
