from abc import ABC, abstractmethod


class ObjectStorageAdapter(ABC):
    @abstractmethod
    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Store bytes at key and return the stored key."""

    @abstractmethod
    def get_bytes(self, key: str) -> bytes | None:
        """Retrieve stored bytes or None if missing."""

    @abstractmethod
    def delete_object(self, key: str) -> bool:
        """Hard-delete object. Returns True if deleted, False if already absent."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return whether an object exists at key."""
