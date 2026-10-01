"""Readiness check. The route only translates DatabaseNotReady into HTTP."""

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

_logger = logging.getLogger("dentacircle.readiness")


class DatabaseNotReady(Exception):
    """The database did not answer. The driver message stays off the response and the log."""


def database_is_ready(session: Session, request_id: str) -> None:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        _logger.error(
            "readiness failed exception_class=%s request_id=%s",
            type(exc).__name__,
            request_id,
        )
        raise DatabaseNotReady from exc
