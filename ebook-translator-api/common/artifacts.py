SQLITE_CONTENT_TYPE = "application/vnd.sqlite3"


def build_job_sqlite_key(user_id: str, job_id: str) -> str:
    return f"result/{user_id}/{job_id}/job.sqlite"
