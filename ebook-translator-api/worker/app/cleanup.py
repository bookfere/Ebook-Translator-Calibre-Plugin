from datetime import datetime, timezone

from common.artifacts import build_job_sqlite_key

from .config import get_settings
from .db import get_connection, insert_event, mark_expired
from .r2 import R2Storage


def cleanup_expired_jobs(limit: int = 500) -> dict:
    settings = get_settings()
    storage = R2Storage(settings)

    with get_connection(settings.database_url) as connection:
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, input_key, output_key
                FROM jobs
                WHERE expires_at < NOW()
                  AND status != 'expired'
                ORDER BY expires_at ASC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

        expired_count = 0
        for row in rows:
            input_key = row["input_key"]
            output_key = row["output_key"]
            storage.delete_objects(settings.r2_raw_bucket, [input_key])
            result_keys = [build_job_sqlite_key(str(row["user_id"]), str(row["id"]))]
            if output_key:
                result_keys.append(output_key)
            storage.delete_objects(settings.r2_result_bucket, result_keys)
            mark_expired(connection, row["id"])
            insert_event(
                connection,
                row["id"],
                row["user_id"],
                "expired",
                "Job expired and objects removed",
            )
            expired_count += 1

    return {"expired": expired_count, "timestamp": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    result = cleanup_expired_jobs()
    print(result)
