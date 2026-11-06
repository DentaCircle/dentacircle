"""Bound the local provider for synchronous staff sends."""

from dentacircle.integrations.messaging.base import (
    Connection,
    IncomingText,
    MessagingProvider,
    SendStatus,
)
from dentacircle.integrations.messaging.bounded import bounded_connection, bounded_send


class BoundedMessagingProvider:
    def __init__(self, provider: MessagingProvider, timeout_seconds: float = 10.0) -> None:
        self.provider = provider
        self.timeout_seconds = timeout_seconds

    def connection(self) -> Connection:
        result = bounded_connection(self.provider, timeout_seconds=self.timeout_seconds)
        return result if isinstance(result, Connection) else Connection("disconnected", False)

    def send_text(self, number: str, body: str, *, fence_fd: int | None = None) -> SendStatus:
        return bounded_send(
            self.provider, number, body, timeout_seconds=self.timeout_seconds, fence_fd=fence_fd
        )

    def normalize_event(self, payload: object) -> IncomingText | None:
        return self.provider.normalize_event(payload)
