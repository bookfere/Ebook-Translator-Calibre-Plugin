from celery import Celery

from .config import get_settings

settings = get_settings()

celery_app = Celery(
    "ebook-translator-worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.task_default_queue = settings.celery_queue_name
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True

celery_app.autodiscover_tasks(["worker_app"])
