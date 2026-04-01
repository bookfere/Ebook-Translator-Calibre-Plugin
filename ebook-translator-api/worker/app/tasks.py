import shutil
import time
from pathlib import Path
from uuid import UUID

from celery import Task
from common.artifacts import build_job_sqlite_key

from .bootstrap_plugin import ensure_plugin_importable
from .celery_app import celery_app
from .config import get_settings
from .db import (
    fetch_job,
    get_connection,
    increment_daily_usage,
    insert_event,
    is_canceled,
    mark_failed,
    mark_processing,
    mark_succeeded,
    update_progress,
)
from .plugin_adapter import run_conversion
from .r2 import R2Storage
from .sqlite_artifact import (
    build_cache_db_path,
    prepare_cache_root,
    upload_sqlite_artifact,
    upsert_artifact_meta,
)


class TranslationTask(Task):
    autoretry_for = ()
    retry_backoff = False
    max_retries = 3


def _upload_sqlite_snapshot(r2: R2Storage, settings, job: dict | None, job_id: str, sqlite_path: Path) -> None:
    if job is None or not sqlite_path.exists():
        return
    upsert_artifact_meta(sqlite_path, job, job_id, job.get("output_key"))
    upload_sqlite_artifact(
        r2,
        settings.r2_result_bucket,
        sqlite_path,
        str(job["user_id"]),
        job_id,
    )


@celery_app.task(bind=True, base=TranslationTask, name="worker.tasks.translate_job")
def translate_job(self, job_id: str) -> dict:
    settings = get_settings()
    retries = settings.retry_schedule

    parsed_job_id = UUID(job_id)
    temp_dir = Path(settings.temp_root) / str(parsed_job_id)
    temp_dir.mkdir(parents=True, exist_ok=True)

    r2 = R2Storage(settings)
    job: dict | None = None
    cache_root = prepare_cache_root(temp_dir)
    input_path = temp_dir / "input.tmp"
    output_path = temp_dir / "output.tmp"
    sqlite_path = cache_root / "cache" / "job.sqlite"

    try:
        with get_connection(settings.database_url) as connection:
            job = fetch_job(connection, parsed_job_id)
            if not job:
                return {"status": "skipped", "reason": "job_not_found"}
            if job["status"] == "canceled":
                return {"status": "skipped", "reason": "job_canceled"}
            if job["status"] == "succeeded":
                return {"status": "skipped", "reason": "already_succeeded"}

            mark_processing(connection, parsed_job_id)
            insert_event(connection, parsed_job_id, job["user_id"], "processing", "Job started")

        input_path = temp_dir / f"input.{job['input_format']}"
        output_path = temp_dir / f"output.{job['output_format']}"
        sqlite_path = build_cache_db_path(job, settings, input_path, cache_root)

        r2.download_file(settings.r2_raw_bucket, job["input_key"], str(input_path))

        with get_connection(settings.database_url) as connection:
            update_progress(connection, parsed_job_id, 5)
            insert_event(
                connection,
                parsed_job_id,
                job["user_id"],
                "input_downloaded",
                "Input file downloaded",
                {"size": input_path.stat().st_size},
            )
            if is_canceled(connection, parsed_job_id):
                insert_event(connection, parsed_job_id, job["user_id"], "canceled", "Job canceled before conversion")
                return {"status": "skipped", "reason": "job_canceled"}

        ensure_plugin_importable(settings.plugin_source_path)

        last_progress_write = 0.0

        def progress_callback(value, _: str = ""):
            nonlocal last_progress_write
            now = time.time()
            progress = int(float(value) * 100) if float(value) <= 1 else int(float(value))
            progress = max(5, min(progress, 95))
            if now - last_progress_write < 2 and progress < 95:
                return
            with get_connection(settings.database_url) as progress_connection:
                update_progress(progress_connection, parsed_job_id, progress)
            last_progress_write = now

        run_conversion(
            job=job,
            settings=settings,
            input_path=input_path,
            output_path=output_path,
            progress_callback=progress_callback,
            cache_path=str(cache_root),
        )
        _upload_sqlite_snapshot(r2, settings, job, job_id, sqlite_path)

        with get_connection(settings.database_url) as connection:
            if is_canceled(connection, parsed_job_id):
                insert_event(connection, parsed_job_id, job["user_id"], "canceled", "Job canceled during processing")
                return {"status": "skipped", "reason": "job_canceled"}

        metadata = r2.upload_file(str(output_path), settings.r2_result_bucket, job["output_key"])

        with get_connection(settings.database_url) as connection:
            mark_succeeded(
                connection,
                parsed_job_id,
                output_key=job["output_key"],
                output_size=metadata.size,
                output_etag=metadata.etag,
            )
            increment_daily_usage(
                connection,
                user_id=job["user_id"],
                bytes_in=0,
                bytes_out=metadata.size,
            )
            insert_event(
                connection,
                parsed_job_id,
                job["user_id"],
                "succeeded",
                "Job completed",
                {"output_size": metadata.size, "output_etag": metadata.etag},
            )

        _upload_sqlite_snapshot(r2, settings, job, job_id, sqlite_path)
        return {"status": "succeeded", "job_id": job_id}

    except Exception as exc:  # noqa: BLE001
        error_message = str(exc)

        if self.request.retries < min(self.max_retries, len(retries)):
            countdown = retries[self.request.retries]
            raise self.retry(exc=exc, countdown=countdown)

        _upload_sqlite_snapshot(r2, settings, job, job_id, sqlite_path)
        with get_connection(settings.database_url) as connection:
            failed_job = fetch_job(connection, parsed_job_id)
            if failed_job:
                mark_failed(connection, parsed_job_id, error_code="PROCESSING_ERROR", error_message=error_message)
                insert_event(
                    connection,
                    parsed_job_id,
                    failed_job["user_id"],
                    "failed",
                    "Job failed",
                    {"error": error_message[:2000]},
                )

        return {"status": "failed", "job_id": job_id, "error": error_message}

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


@celery_app.task(bind=True, base=TranslationTask, name="worker.tasks.rebuild_job")
def rebuild_job(self, job_id: str) -> dict:
    settings = get_settings()
    retries = settings.retry_schedule

    parsed_job_id = UUID(job_id)
    temp_dir = Path(settings.temp_root) / str(parsed_job_id)
    temp_dir.mkdir(parents=True, exist_ok=True)

    r2 = R2Storage(settings)
    job: dict | None = None
    cache_root = prepare_cache_root(temp_dir)
    input_path = temp_dir / "input.tmp"
    output_path = temp_dir / "output.tmp"
    sqlite_path = cache_root / "cache" / "job.sqlite"

    try:
        with get_connection(settings.database_url) as connection:
            job = fetch_job(connection, parsed_job_id)
            if not job:
                return {"status": "skipped", "reason": "job_not_found"}
            if job["status"] == "expired":
                return {"status": "skipped", "reason": "job_expired"}
            if job["status"] == "canceled":
                return {"status": "skipped", "reason": "job_canceled"}
            if job["status"] == "processing":
                return {"status": "skipped", "reason": "job_processing"}

            mark_processing(connection, parsed_job_id)
            insert_event(connection, parsed_job_id, job["user_id"], "rebuild_processing", "Job rebuild started")

        input_path = temp_dir / f"input.{job['input_format']}"
        output_path = temp_dir / f"output.{job['output_format']}"
        sqlite_path = build_cache_db_path(job, settings, input_path, cache_root)

        r2.download_file(settings.r2_raw_bucket, job["input_key"], str(input_path))
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        r2.download_file(
            settings.r2_result_bucket,
            build_job_sqlite_key(str(job["user_id"]), str(parsed_job_id)),
            str(sqlite_path),
        )

        with get_connection(settings.database_url) as connection:
            update_progress(connection, parsed_job_id, 5)
            insert_event(
                connection,
                parsed_job_id,
                job["user_id"],
                "rebuild_input_downloaded",
                "Rebuild inputs downloaded",
                {"sqlite_size": sqlite_path.stat().st_size, "input_size": input_path.stat().st_size},
            )
            if is_canceled(connection, parsed_job_id):
                insert_event(connection, parsed_job_id, job["user_id"], "canceled", "Job canceled before rebuild")
                return {"status": "skipped", "reason": "job_canceled"}

        ensure_plugin_importable(settings.plugin_source_path)

        last_progress_write = 0.0

        def progress_callback(value, _: str = ""):
            nonlocal last_progress_write
            now = time.time()
            progress = int(float(value) * 100) if float(value) <= 1 else int(float(value))
            progress = max(5, min(progress, 95))
            if now - last_progress_write < 2 and progress < 95:
                return
            with get_connection(settings.database_url) as progress_connection:
                update_progress(progress_connection, parsed_job_id, progress)
            last_progress_write = now

        run_conversion(
            job=job,
            settings=settings,
            input_path=input_path,
            output_path=output_path,
            progress_callback=progress_callback,
            cache_path=str(cache_root),
            cache_only=True,
        )
        _upload_sqlite_snapshot(r2, settings, job, job_id, sqlite_path)

        with get_connection(settings.database_url) as connection:
            if is_canceled(connection, parsed_job_id):
                insert_event(connection, parsed_job_id, job["user_id"], "canceled", "Job canceled during rebuild")
                return {"status": "skipped", "reason": "job_canceled"}

        metadata = r2.upload_file(str(output_path), settings.r2_result_bucket, job["output_key"])

        with get_connection(settings.database_url) as connection:
            mark_succeeded(
                connection,
                parsed_job_id,
                output_key=job["output_key"],
                output_size=metadata.size,
                output_etag=metadata.etag,
            )
            increment_daily_usage(
                connection,
                user_id=job["user_id"],
                bytes_in=0,
                bytes_out=metadata.size,
            )
            insert_event(
                connection,
                parsed_job_id,
                job["user_id"],
                "rebuild_succeeded",
                "Job rebuild completed",
                {"output_size": metadata.size, "output_etag": metadata.etag},
            )

        _upload_sqlite_snapshot(r2, settings, job, job_id, sqlite_path)
        return {"status": "succeeded", "job_id": job_id}

    except Exception as exc:  # noqa: BLE001
        error_message = str(exc)

        if self.request.retries < min(self.max_retries, len(retries)):
            countdown = retries[self.request.retries]
            raise self.retry(exc=exc, countdown=countdown)

        _upload_sqlite_snapshot(r2, settings, job, job_id, sqlite_path)
        with get_connection(settings.database_url) as connection:
            failed_job = fetch_job(connection, parsed_job_id)
            if failed_job:
                mark_failed(connection, parsed_job_id, error_code="PROCESSING_ERROR", error_message=error_message)
                insert_event(
                    connection,
                    parsed_job_id,
                    failed_job["user_id"],
                    "rebuild_failed",
                    "Job rebuild failed",
                    {"error": error_message[:2000]},
                )

        return {"status": "failed", "job_id": job_id, "error": error_message}

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
