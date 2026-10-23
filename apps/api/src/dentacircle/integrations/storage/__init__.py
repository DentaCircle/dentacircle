"""Storage for document bytes. Core code imports DocumentStorage and get_storage from here."""

from pathlib import Path

from dentacircle.core.config import get_settings, repo_root
from dentacircle.integrations.storage.base import (
    DocumentStorage,
    StorageKeyError,
    StorageNotFoundError,
)
from dentacircle.integrations.storage.local import LocalDiskStorage


def get_storage() -> DocumentStorage:
    """The configured adapter. The only one is the local disk under STORAGE_ROOT."""
    root = Path(get_settings().storage_root)
    if not root.is_absolute():
        root = repo_root() / root
    return LocalDiskStorage(root)


__all__ = ["DocumentStorage", "StorageKeyError", "StorageNotFoundError", "get_storage"]
