import json
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


@contextmanager
def get_connection(database_url: str):
    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as connection:
        yield connection


def fetch_job(connection: psycopg.Connection, job_id: UUID) -> dict | None:
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
        return cur.fetchone()


def insert_event(
    connection: psycopg.Connection,
    job_id: UUID,
    user_id: str,
    event_type: str,
    message: str,
    details: dict | None = None,
) -> None:
    payload = details or {}
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO job_events (job_id, user_id, event_type, message, details)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (job_id, user_id, event_type, message, json.dumps(payload)),
        )


def mark_processing(connection: psycopg.Connection, job_id: UUID) -> None:
    with connection.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs
            SET status = 'processing', started_at = NOW(), progress = GREATEST(progress, 1)
            WHERE id = %s AND status = 'queued'
            """,
            (job_id,),
        )


def mark_rebuild_queued(connection: psycopg.Connection, job_id: UUID) -> None:
    with connection.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs
            SET status = 'queued',
                progress = 0,
                started_at = NULL,
                finished_at = NULL,
                error_code = NULL,
                error_message = NULL
            WHERE id = %s AND status IN ('succeeded', 'failed', 'canceled')
            """,
            (job_id,),
        )


def update_progress(connection: psycopg.Connection, job_id: UUID, progress: int) -> None:
    progress = max(0, min(progress, 99))
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET progress = GREATEST(progress, %s) WHERE id = %s",
            (progress, job_id),
        )


def mark_succeeded(
    connection: psycopg.Connection,
    job_id: UUID,
    output_key: str,
    output_size: int,
    output_etag: str | None,
) -> None:
    with connection.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs
            SET status = 'succeeded', progress = 100,
                output_key = %s,
                output_size = %s,
                output_etag = %s,
                finished_at = NOW(),
                error_code = NULL,
                error_message = NULL
            WHERE id = %s
            """,
            (output_key, output_size, output_etag, job_id),
        )


def mark_failed(connection: psycopg.Connection, job_id: UUID, error_code: str, error_message: str) -> None:
    with connection.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs
            SET status = 'failed',
                finished_at = NOW(),
                error_code = %s,
                error_message = %s,
                progress = LEAST(progress, 99)
            WHERE id = %s
            """,
            (error_code, error_message[:2000], job_id),
        )


def is_canceled(connection: psycopg.Connection, job_id: UUID) -> bool:
    with connection.cursor() as cur:
        cur.execute("SELECT status = 'canceled' AS canceled FROM jobs WHERE id = %s", (job_id,))
        row = cur.fetchone()
    return bool(row and row["canceled"])


def mark_expired(connection: psycopg.Connection, job_id: UUID) -> None:
    with connection.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs
            SET status = 'expired', finished_at = COALESCE(finished_at, NOW())
            WHERE id = %s AND status IN ('queued', 'processing', 'succeeded', 'failed', 'canceled')
            """,
            (job_id,),
        )


def increment_daily_usage(
    connection: psycopg.Connection,
    user_id: str,
    bytes_in: int,
    bytes_out: int,
    jobs_increment: int = 0,
) -> None:
    usage_date = datetime.now(timezone.utc).date()
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO usage_daily (user_id, usage_date, jobs_created, bytes_in, bytes_out)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, usage_date)
            DO UPDATE SET
                jobs_created = usage_daily.jobs_created + EXCLUDED.jobs_created,
                bytes_in = usage_daily.bytes_in + EXCLUDED.bytes_in,
                bytes_out = usage_daily.bytes_out + EXCLUDED.bytes_out
            """,
            (user_id, usage_date, jobs_increment, bytes_in, bytes_out),
        )
