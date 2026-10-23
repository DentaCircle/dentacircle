"""Document storage in memory, for tests. Nothing touches the disk."""

from collections.abc import Iterator

from dentacircle.integrations.storage.base import CHUNK_SIZE, StorageNotFoundError, check_key


class MemoryStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        check_key(key)
        self.files[key] = data

    def open(self, key: str) -> Iterator[bytes]:
        check_key(key)
        data = self.files.get(key)
        if data is None:
            raise StorageNotFoundError
        return _chunks(data)

    def delete(self, key: str) -> None:
        check_key(key)
        self.files.pop(key, None)


def _chunks(data: bytes) -> Iterator[bytes]:
    for start in range(0, len(data), CHUNK_SIZE):
        yield data[start : start + CHUNK_SIZE]
