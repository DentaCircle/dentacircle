"""The storage interface: one contract for both adapters, key escapes, and the import guard."""

import ast
import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from dentacircle.core.config import StartupError, get_settings
from dentacircle.integrations.storage import get_storage
from dentacircle.integrations.storage.base import (
    CHUNK_SIZE,
    DocumentStorage,
    StorageKeyError,
    StorageNotFoundError,
)
from dentacircle.integrations.storage.local import LocalDiskStorage
from dentacircle.integrations.storage.memory import MemoryStorage

_KEY = "11111111-1111-1111-1111-111111111111/22222222-2222-2222-2222-222222222222"
_BAD_KEYS = [
    "",
    "..",
    "../outside",
    "a/../../outside",
    "a/..",
    "/absolute/path",
    "a//b",
    "a/./b",
    "./a",
    "a\\b",
    "a/b/",
    "a\x00b",
]


@pytest.fixture(params=["local", "memory"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> DocumentStorage:
    if request.param == "local":
        return LocalDiskStorage(tmp_path / "root")
    return MemoryStorage()


def _read(storage: DocumentStorage, key: str) -> bytes:
    return b"".join(storage.open(key))


def test_put_then_open_returns_the_same_bytes(storage: DocumentStorage) -> None:
    storage.put(_KEY, b"synthetic bytes")
    assert _read(storage, _KEY) == b"synthetic bytes"


def test_a_large_file_comes_back_in_chunks(storage: DocumentStorage) -> None:
    data = bytes(range(256)) * (CHUNK_SIZE // 256 * 2 + 3)
    storage.put(_KEY, data)
    chunks = list(storage.open(_KEY))
    assert len(chunks) == 3
    assert all(len(chunk) <= CHUNK_SIZE for chunk in chunks)
    assert b"".join(chunks) == data


def test_put_again_replaces_the_bytes(storage: DocumentStorage) -> None:
    storage.put(_KEY, b"first")
    storage.put(_KEY, b"second")
    assert _read(storage, _KEY) == b"second"


def test_open_of_a_missing_key_fails_before_any_chunk(storage: DocumentStorage) -> None:
    with pytest.raises(StorageNotFoundError):
        storage.open(_KEY)


def test_delete_removes_the_bytes_and_is_safe_twice(storage: DocumentStorage) -> None:
    storage.put(_KEY, b"synthetic bytes")
    storage.delete(_KEY)
    with pytest.raises(StorageNotFoundError):
        storage.open(_KEY)
    storage.delete(_KEY)


@pytest.mark.parametrize("key", _BAD_KEYS)
def test_a_key_that_could_leave_the_root_is_refused(storage: DocumentStorage, key: str) -> None:
    operations: list[Callable[[], object]] = [
        lambda: storage.put(key, b"x"),
        lambda: storage.open(key),
        lambda: storage.delete(key),
    ]
    for operation in operations:
        with pytest.raises(StorageKeyError):
            operation()


def test_a_refused_key_writes_nothing_outside_the_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    local = LocalDiskStorage(root)
    for key in ("../outside", "a/../../outside", "/etc/outside"):
        with pytest.raises(StorageKeyError):
            local.put(key, b"x")
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == []


def test_a_symlink_that_leads_out_of_the_root_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "clinic").symlink_to(outside, target_is_directory=True)
    with pytest.raises(StorageKeyError):
        LocalDiskStorage(root).put("clinic/file", b"x")
    assert list(outside.iterdir()) == []


def test_a_failed_write_leaves_no_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = LocalDiskStorage(tmp_path / "root")

    def fail(self: Path, target: object) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError):
        local.put(_KEY, b"x")
    assert [path for path in (tmp_path / "root").rglob("*") if path.is_file()] == []


@pytest.mark.skipif(sys.platform == "win32", reason="directory fsync is skipped on Windows")
def test_a_failed_directory_fsync_removes_the_new_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = LocalDiskStorage(tmp_path / "root")
    real_fsync = os.fsync
    calls = 0

    def fail_on_directory_fsync(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("fsync failed")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_on_directory_fsync)
    with pytest.raises(OSError):
        local.put(_KEY, b"x")
    assert [path for path in (tmp_path / "root").rglob("*") if path.is_file()] == []


def test_get_storage_uses_storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/x")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "docs"))
    get_storage().put(_KEY, b"synthetic bytes")
    assert (tmp_path / "docs" / _KEY).read_bytes() == b"synthetic bytes"


def test_storage_root_defaults_under_the_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/x")
    monkeypatch.delenv("STORAGE_ROOT", raising=False)
    assert get_settings().storage_root == ".data/documents"


def test_a_blank_storage_root_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/x")
    monkeypatch.setenv("STORAGE_ROOT", "  ")
    with pytest.raises(StartupError) as caught:
        get_settings()
    assert "STORAGE_ROOT" in str(caught.value)


# --- the import guard -------------------------------------------------------

_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "dentacircle"
_ADAPTERS = ("dentacircle.integrations.storage.local", "dentacircle.integrations.storage.memory")
_FILE_MODULES = ("pathlib", "shutil", "tempfile", "os", "io")


def _imported(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _calls_open(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"
        for node in ast.walk(tree)
    )


def _modules(*folders: str) -> list[Path]:
    return sorted(path for folder in folders for path in (_PACKAGE / folder).rglob("*.py"))


def test_only_the_storage_package_imports_an_adapter() -> None:
    offenders = []
    for path in _PACKAGE.rglob("*.py"):
        if "integrations" in path.relative_to(_PACKAGE).parts:
            continue
        if _imported(ast.parse(path.read_text())) & set(_ADAPTERS):
            offenders.append(path.name)
    assert offenders == []


def test_services_and_routes_never_touch_the_file_system() -> None:
    offenders = []
    for path in _modules("services", "api", "repositories", "domain"):
        tree = ast.parse(path.read_text())
        modules = {name.split(".")[0] for name in _imported(tree)}
        if modules & set(_FILE_MODULES) or _calls_open(tree):
            offenders.append(path.name)
    assert offenders == []


def test_the_guard_catches_a_violation() -> None:
    bad = ast.parse("from pathlib import Path\nopen('x')\n")
    assert {name.split(".")[0] for name in _imported(bad)} & set(_FILE_MODULES)
    assert _calls_open(bad)
    adapter = ast.parse("from dentacircle.integrations.storage.local import LocalDiskStorage\n")
    assert _imported(adapter) & set(_ADAPTERS)
