"""Provider-independent messaging contracts."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

ConnectionStatus = Literal["connected", "disconnected", "unconfigured"]
SendStatus = Literal["accepted", "failed", "unknown"]


@dataclass(frozen=True)
class Connection:
    status: ConnectionStatus
    can_send_text: bool


@dataclass(frozen=True)
class SendReceipt:
    status: SendStatus
    provider_message_id: str | None = None


@dataclass(frozen=True)
class IncomingText:
    account_key: str
    number: str
    provider_message_id: str
    body: str
    provider_sent_at: datetime | None
    quoted_stanza_id: str | None = None


class MessagingProvider(Protocol):
    def connection(self) -> Connection: ...

    def send_text(self, number: str, body: str, *, fence_fd: int | None = None) -> SendStatus: ...

    def normalize_event(self, payload: object) -> IncomingText | None: ...
