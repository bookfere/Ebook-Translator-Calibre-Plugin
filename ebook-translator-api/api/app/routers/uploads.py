from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import AuthContext, get_auth_context
from ..config import Settings, get_settings
from ..models import UploadInitRequest, UploadInitResponse
from ..r2 import R2Client, get_r2_client

router = APIRouter(prefix="/v1", tags=["uploads"])


@router.post("/uploads:init", response_model=UploadInitResponse)
async def init_upload(
    request: UploadInitRequest,
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
    r2: R2Client = Depends(get_r2_client),
) -> UploadInitResponse:
    input_format = request.input_format.lower()
    if input_format not in settings.allowed_input_formats:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported input format")

    job_id = uuid4()
    key = f"raw/{auth.user_id}/{job_id}/input.{input_format}"
    put_url = r2.presign_put(
        bucket=settings.r2_raw_bucket,
        key=key,
        content_type=request.content_type,
        expires=settings.presigned_put_expires_seconds,
    )

    return UploadInitResponse(
        upload_key=str(job_id),
        put_url=put_url,
        expires_in_seconds=settings.presigned_put_expires_seconds,
    )
