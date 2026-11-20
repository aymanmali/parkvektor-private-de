from functools import lru_cache

from app.adapters.storage.base import ObjectStorageAdapter
from app.adapters.storage.local_storage import LocalFilesystemStorageAdapter
from app.adapters.storage.s3_storage import S3StorageAdapter
from app.core.config import get_settings


@lru_cache
def get_storage_adapter() -> ObjectStorageAdapter:
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3StorageAdapter(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
        )
    return LocalFilesystemStorageAdapter(settings.local_storage_dir)
