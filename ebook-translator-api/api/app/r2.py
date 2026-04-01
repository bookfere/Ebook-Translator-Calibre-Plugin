from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError
from fastapi import Depends

from .config import Settings, get_settings


class R2ObjectNotFound(Exception):
    pass


@dataclass
class ObjectMetadata:
    size: int
    content_type: str | None
    etag: str | None


class R2Client:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name=settings.r2_region,
        )

    def presign_put(self, bucket: str, key: str, content_type: str, expires: int) -> str:
        return self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires,
        )

    def presign_get(self, bucket: str, key: str, expires: int) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires,
        )

    def head_object(self, bucket: str, key: str) -> ObjectMetadata:
        try:
            response = self.client.head_object(Bucket=bucket, Key=key)
            return ObjectMetadata(
                size=response["ContentLength"],
                content_type=response.get("ContentType"),
                etag=(response.get("ETag") or "").strip('"') or None,
            )
        except ClientError as exc:
            status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status_code == 404:
                raise R2ObjectNotFound(key) from exc
            raise


def get_r2_client(settings: Settings = Depends(get_settings)) -> R2Client:
    return R2Client(settings)
