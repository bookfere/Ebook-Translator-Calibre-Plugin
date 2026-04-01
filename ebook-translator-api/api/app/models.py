from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    EXPIRED = "expired"


class UploadInitRequest(BaseModel):
    input_format: str
    content_type: str = "application/octet-stream"


class UploadInitResponse(BaseModel):
    upload_key: str
    put_url: str
    expires_in_seconds: int


class CreateJobRequest(BaseModel):
    upload_key: str
    input_format: str
    output_format: str
    source_lang: str
    target_lang: str
    engine: str
    engine_options: dict = Field(default_factory=dict)


class CreateJobResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    created_at: datetime


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: UUID
    status: JobStatus
    progress: int
    error_code: str | None
    error_message: str | None
    input_key: str
    output_key: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    expires_at: datetime


class JobListResponse(BaseModel):
    items: list[JobResponse]
    limit: int
    offset: int


class CancelJobResponse(BaseModel):
    job_id: UUID
    status: JobStatus


class DownloadUrlResponse(BaseModel):
    job_id: UUID
    download_url: str
    expires_in_seconds: int


class ArtifactUrlResponse(BaseModel):
    job_id: UUID
    url: str
    expires_in_seconds: int


class RebuildJobResponse(BaseModel):
    job_id: UUID
    status: JobStatus


class EngineInfo(BaseModel):
    id: str
    display_name: str


class FormatInfo(BaseModel):
    input_formats: list[str]
    output_formats: list[str]


class AdminMetricsResponse(BaseModel):
    jobs_total_24h: int
    jobs_success_24h: int
    jobs_failed_24h: int
    job_success_rate_24h: float
    queue_depth: int
