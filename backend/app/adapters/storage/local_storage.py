from pathlib import Path

from app.adapters.storage.base import ObjectStorageAdapter


class LocalFilesystemStorageAdapter(ObjectStorageAdapter):
    """Local disk storage adapter for zero-Docker development & automated DSGVO purge tests."""

    def __init__(self, base_dir: str) -> None:
        self.base_path = Path(base_dir).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, key: str) -> Path:
        clean = key.lstrip("/")
        resolved = (self.base_path / clean).resolve()
        if not str(resolved).startswith(str(self.base_path)):
            raise ValueError("Invalid storage key path traversal attempt")
        return resolved

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._safe_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get_bytes(self, key: str) -> bytes | None:
        path = self._safe_path(key)
        if not path.is_file():
            return None
        return path.read_bytes()

    def delete_object(self, key: str) -> bool:
        path = self._safe_path(key)
        if path.is_file():
            path.unlink()
            return True
        return False

    def exists(self, key: str) -> bool:
        return self._safe_path(key).is_file()
