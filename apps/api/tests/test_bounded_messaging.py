"""The dispatcher uses a wall-clock bound rather than an inactivity timeout."""

import time

import pytest

from dentacircle.integrations.messaging.base import (
    Connection,
    IncomingText,
    SendReceipt,
    SendStatus,
)
from dentacircle.integrations.messaging.bounded import bounded_send, bounded_send_receipt


class SlowProvider:
    def connection(self) -> Connection:
        return Connection("connected", True)

    def send_text(self, number: str, body: str, *, fence_fd: int | None = None) -> SendStatus:
        time.sleep(5)
        return "accepted"

    def normalize_event(self, payload: object) -> IncomingText | None:
        return None


class AcceptedProvider(SlowProvider):
    def send_text(self, number: str, body: str, *, fence_fd: int | None = None) -> SendStatus:
        return "accepted"


class ReceiptProvider(AcceptedProvider):
    def send_text_receipt(self, number: str, body: str) -> SendReceipt:
        return SendReceipt("accepted", "true_chat_STANZA123")


def test_bounded_send_retains_provider_receipt() -> None:
    result = bounded_send_receipt(ReceiptProvider(), "+15551234567", "hello", timeout_seconds=3)
    assert result == SendReceipt("accepted", "true_chat_STANZA123")


def test_bounded_send_cuts_off_a_stuck_provider() -> None:
    start = time.monotonic()
    result = bounded_send(SlowProvider(), "+15551234567", "hello", timeout_seconds=0.5)
    assert result == "unknown"
    assert time.monotonic() - start < 3


def test_bounded_send_preserves_a_provider_acceptance() -> None:
    assert (
        bounded_send(AcceptedProvider(), "+15551234567", "hello", timeout_seconds=3) == "accepted"
    )


def test_startup_failure_releases_shared_contact_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import multiprocessing
    import os
    from uuid import uuid4

    from dentacircle.integrations.messaging import bounded
    from dentacircle.integrations.messaging.contact_fence import contact_fence

    real_context = multiprocessing.get_context("spawn")

    class FailedProcess:
        def start(self) -> None:
            raise OSError("simulated child startup failure")

    class FailedContext:
        @staticmethod
        def Pipe(duplex: bool) -> object:
            return real_context.Pipe(duplex=duplex)

        @staticmethod
        def Process(*, target: object, args: tuple[object, ...]) -> FailedProcess:
            return FailedProcess()

    class DuplicatedFence:
        def __init__(self, fd: int) -> None:
            self.fd = os.dup(fd)

        def detach(self) -> int:
            fd, self.fd = self.fd, -1
            if fd < 0:
                raise OSError("fence already detached")
            return fd

    monkeypatch.setattr(multiprocessing, "get_context", lambda _method: FailedContext())
    monkeypatch.setattr(bounded, "DupFd", DuplicatedFence)
    clinic_id, contact_id = uuid4(), uuid4()
    with contact_fence(clinic_id, contact_id) as fd:
        assert fd is not None
        assert (
            bounded_send(
                AcceptedProvider(), "+15551234567", "hello", timeout_seconds=1, fence_fd=fd
            )
            == "unknown"
        )

    # If the DupFd duplicate remains registered, it keeps the flock held here.
    with contact_fence(clinic_id, contact_id) as fd:
        assert fd is not None


class SlowConnectionProvider(SlowProvider):
    def connection(self) -> Connection:
        time.sleep(5)
        return Connection("connected", True)


def test_staff_provider_wrapper_bounds_send_and_connection() -> None:
    from dentacircle.integrations.messaging.bounded_provider import BoundedMessagingProvider

    start = time.monotonic()
    assert (
        BoundedMessagingProvider(SlowProvider(), 0.5).send_text("+15551234567", "hello")
        == "unknown"
    )
    assert (
        BoundedMessagingProvider(SlowConnectionProvider(), 0.5).connection().status
        == "disconnected"
    )
    assert time.monotonic() - start < 4
