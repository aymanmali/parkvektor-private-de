import boto3
from botocore.exceptions import ClientError

from app.adapters.storage.base import ObjectStorageAdapter


class S3StorageAdapter(ObjectStorageAdapter):
    """S3-compatible storage adapter for Frankfurt AWS S3, Hetzner Object Storage, or local MinIO."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str = "eu-central-1",
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except ClientError:
                pass

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    def get_bytes(self, key: str) -> bytes | None:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read()
        except ClientError:
            return None

    def delete_object(self, key: str) -> bool:
        if not self.exists(key):
            return False
        self.client.delete_object(Bucket=self.bucket, Key=key)
        return True

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False
