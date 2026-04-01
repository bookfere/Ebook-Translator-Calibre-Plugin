import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from common.artifacts import build_job_sqlite_key

from .config import Settings
from .runtime_config import map_engine_name, normalize_engine_options


def prepare_cache_root(temp_dir: Path) -> Path:
    cache_root = temp_dir / "runtime-cache"
    (cache_root / "cache").mkdir(parents=True, exist_ok=True)
    (cache_root / "temp").mkdir(parents=True, exist_ok=True)
    return cache_root


def build_cache_db_path(
    job: dict,
    settings: Settings,
    input_path: Path,
    cache_root: Path,
    encoding: str = "utf-8",
) -> Path:
    options = normalize_engine_options(job.get("engine_options"))
    merge_length = int(options.get("merge_length", 1800)) if bool(options.get("merge_enabled", False)) else 0
    md5 = hashlib.md5()
    extra_encoding = "" if encoding.lower() == "utf-8" else encoding.lower()
    identity = f"{input_path}{map_engine_name(job['engine'], settings)}{job['target_lang']}{merge_length}{extra_encoding}"
    md5.update(identity.encode("utf-8"))
    return cache_root / "cache" / f"{md5.hexdigest()}.db"


def upsert_artifact_meta(sqlite_path: Path, job: dict, job_id: str, output_key: str | None) -> None:
    if not sqlite_path.exists():
        return

    metadata = {
        "schema_version": "1",
        "job_id": str(job_id),
        "user_id": str(job["user_id"]),
        "input_format": str(job["input_format"]),
        "output_format": str(job["output_format"]),
        "source_lang": str(job["source_lang"]),
        "target_lang": str(job["target_lang"]),
        "engine": str(job["engine"]),
        "output_key": output_key or "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "engine_options": json.dumps(normalize_engine_options(job.get("engine_options"))),
    }

    with sqlite3.connect(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS review_status(
                id PRIMARY KEY,
                error_message DEFAULT NULL,
                edited_at DEFAULT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS artifact_meta(
                key PRIMARY KEY,
                value DEFAULT NULL
            )
            """
        )
        for key, value in metadata.items():
            cursor.execute(
                """
                INSERT INTO artifact_meta(key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (key, value),
            )
        connection.commit()


def upload_sqlite_artifact(storage, bucket: str, sqlite_path: Path, user_id: str, job_id: str):
    if not sqlite_path.exists():
        return None
    return storage.upload_file(
        str(sqlite_path),
        bucket,
        build_job_sqlite_key(user_id, job_id),
        content_type="application/vnd.sqlite3",
    )
