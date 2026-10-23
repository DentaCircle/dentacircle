"""The storage interface for document bytes. Keys are opaque strings built by the server."""

from collections.abc import Iterator
from typing import Protocol

CHUNK_SIZE = 64 * 1024


class StorageKeyError(Exception):
    """The key is not a plain relative path made of safe segments."""


class StorageNotFoundError(Exception):
    """No bytes are stored under this key."""


class DocumentStorage(Protocol):
    """Put, read and delete whole files by key. An adapter never sees a filename."""

    def put(self, key: str, data: bytes) -> None:
        """Store the bytes under the key, replacing anything already there."""
        ...

    def open(self, key: str) -> Iterator[bytes]:
        """Read the bytes in chunks. Raises StorageNotFoundError before the first chunk."""
        ...

    def delete(self, key: str) -> None:
        """Remove the bytes. A key with nothing stored is not an error."""
        ...


def check_key(key: str) -> None:
    """Refuse an empty key, an absolute path, a backslash, a NUL and any `.` or `..` segment."""
    if not key or key.startswith("/") or "\\" in key or "\x00" in key:
        raise StorageKeyError
    if any(segment in ("", ".", "..") for segment in key.split("/")):
        raise StorageKeyError
