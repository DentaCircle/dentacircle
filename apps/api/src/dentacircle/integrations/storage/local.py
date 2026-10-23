"""Document storage on the local disk, under one root folder."""

from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from dentacircle.integrations.storage.base import (
    CHUNK_SIZE,
    StorageKeyError,
    StorageNotFoundError,
    check_key,
)


class LocalDiskStorage:
    def __init__(self, root: Path) -> None:
        self._root = root

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write beside the target and rename, so a reader never sees half a file.
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def open(self, key: str) -> Iterator[bytes]:
        try:
            handle = self._path(key).open("rb")
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
            raise StorageNotFoundError from None
        return _read_chunks(handle)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def _path(self, key: str) -> Path:
        check_key(key)
        root = self._root.resolve()
        path = (root / key).resolve()
        # A symlink inside the root can still lead out of it.
        if not path.is_relative_to(root):
            raise StorageKeyError
        return path


def _read_chunks(handle: BinaryIO) -> Iterator[bytes]:
    with handle:
        while chunk := handle.read(CHUNK_SIZE):
            yield chunk
