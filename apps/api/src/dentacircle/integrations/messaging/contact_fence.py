"""A local process fence serializes sends for a clinic contact."""

import fcntl
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID


@contextmanager
def contact_fence(clinic_id: UUID, contact_id: UUID) -> Iterator[int | None]:
    """Keep fence files after use so later processes cannot lock different inodes."""
    root = Path(tempfile.gettempdir()) / "dentacircle-dispatch-v1"
    root.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(root / f"{clinic_id}-{contact_id}", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield None
            return
        yield fd
    finally:
        os.close(fd)
