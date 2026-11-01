"""Messaging provider boundary."""

from dentacircle.integrations.messaging.base import (
    Connection,
    IncomingText,
    MessagingProvider,
    SendStatus,
)

__all__ = ["Connection", "IncomingText", "MessagingProvider", "SendStatus"]
