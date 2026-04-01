from celery import Celery
from fastapi import Depends

from .config import Settings, get_settings


class QueuePublisher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = Celery("ebook-translator-api", broker=settings.redis_url, backend=settings.redis_url)

    def enqueue_translation_job(self, job_id: str) -> str:
        result = self.client.send_task(
            "worker.tasks.translate_job",
            kwargs={"job_id": job_id},
            queue=self.settings.celery_queue_name,
        )
        return result.id

    def enqueue_rebuild_job(self, job_id: str) -> str:
        result = self.client.send_task(
            "worker.tasks.rebuild_job",
            kwargs={"job_id": job_id},
            queue=self.settings.celery_queue_name,
        )
        return result.id


def get_queue_publisher(settings: Settings = Depends(get_settings)) -> QueuePublisher:
    return QueuePublisher(settings)
