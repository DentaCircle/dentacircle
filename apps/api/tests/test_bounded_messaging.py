"""The dispatcher uses a wall-clock bound rather than an inactivity timeout."""

import time

from dentacircle.integrations.messaging.base import Connection, IncomingText, SendStatus
from dentacircle.integrations.messaging.bounded import bounded_send


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


def test_bounded_send_cuts_off_a_stuck_provider() -> None:
    start = time.monotonic()
    result = bounded_send(SlowProvider(), "+15551234567", "hello", timeout_seconds=0.5)
    assert result == "unknown"
    assert time.monotonic() - start < 3


def test_bounded_send_preserves_a_provider_acceptance() -> None:
    assert (
        bounded_send(AcceptedProvider(), "+15551234567", "hello", timeout_seconds=3) == "accepted"
    )


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
