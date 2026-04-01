import redis.asyncio as redis
import asyncpg
from fastapi import APIRouter, Depends

from ..auth import AuthContext, require_admin
from ..config import Settings, get_settings
from ..db import get_connection
from ..models import AdminMetricsResponse

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/metrics", response_model=AdminMetricsResponse)
async def get_admin_metrics(
    _: AuthContext = Depends(require_admin),
    settings: Settings = Depends(get_settings),
    conn: asyncpg.Connection = Depends(get_connection),
) -> AdminMetricsResponse:
    row = await conn.fetchrow(
        """
        SELECT
            COUNT(*)::int AS jobs_total,
            COUNT(*) FILTER (WHERE status = 'succeeded')::int AS jobs_success,
            COUNT(*) FILTER (WHERE status = 'failed')::int AS jobs_failed
        FROM jobs
        WHERE created_at >= NOW() - INTERVAL '24 hours'
        """
    )

    jobs_total = row["jobs_total"]
    jobs_success = row["jobs_success"]
    jobs_failed = row["jobs_failed"]
    success_rate = 0.0 if jobs_total == 0 else round((jobs_success / jobs_total) * 100, 2)

    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        queue_depth_raw = await redis_client.llen(settings.celery_queue_name)
        queue_depth = int(queue_depth_raw or 0)
    except Exception:  # noqa: BLE001
        queue_depth = 0
    finally:
        await redis_client.aclose()

    return AdminMetricsResponse(
        jobs_total_24h=jobs_total,
        jobs_success_24h=jobs_success,
        jobs_failed_24h=jobs_failed,
        job_success_rate_24h=success_rate,
        queue_depth=queue_depth,
    )
