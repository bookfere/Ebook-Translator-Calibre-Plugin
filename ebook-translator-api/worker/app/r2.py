from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

from .config import Settings


class ObjectNotFoundError(Exception):
    pass


@dataclass
class ObjectMetadata:
    size: int
    etag: str | None
    content_type: str | None


class R2Storage:
    def __init__(self, settings: Settings):
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name=settings.r2_region,
        )

    def download_file(self, bucket: str, key: str, local_path: str) -> None:
        self.client.download_file(bucket, key, local_path)

    def upload_file(self, local_path: str, bucket: str, key: str, content_type: str | None = None) -> ObjectMetadata:
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        self.client.upload_file(local_path, bucket, key, ExtraArgs=extra_args)
        return self.head_object(bucket, key)

    def head_object(self, bucket: str, key: str) -> ObjectMetadata:
        try:
            response = self.client.head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code == 404:
                raise ObjectNotFoundError(key) from exc
            raise

        return ObjectMetadata(
            size=response["ContentLength"],
            etag=(response.get("ETag") or "").strip('"') or None,
            content_type=response.get("ContentType"),
        )

    def delete_objects(self, bucket: str, keys: list[str]) -> None:
        if not keys:
            return
        objects = [{"Key": key} for key in keys]
        self.client.delete_objects(Bucket=bucket, Delete={"Objects": objects, "Quiet": True})
