"""Bound a provider call while retaining the caller's process fence."""

import multiprocessing
import os
import signal
from multiprocessing.connection import Connection
from multiprocessing.reduction import DupFd
from typing import Any, cast

from dentacircle.integrations.messaging.base import MessagingProvider, SendStatus


def _timeout(_signal: int, _frame: object) -> None:
    raise TimeoutError


def _send(
    provider: MessagingProvider,
    number: str,
    body: str,
    output: Connection,
    shared_fence: Any,
    timeout_seconds: float,
) -> None:
    fence_fd: int | None = None
    try:
        if shared_fence is not None:
            fence_fd = shared_fence.detach()
        signal.signal(signal.SIGALRM, _timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        connection = provider.connection()
        result = (
            provider.send_text(number, body)
            if connection.status == "connected" and connection.can_send_text
            else "failed"
        )
        output.send(result if result in ("accepted", "failed", "unknown") else "unknown")
    except Exception:
        try:
            output.send("unknown")
        except (BrokenPipeError, OSError):
            pass
    finally:
        output.close()
        if fence_fd is not None:
            os.close(fence_fd)


def bounded_send(
    provider: MessagingProvider,
    number: str,
    body: str,
    *,
    timeout_seconds: float,
    fence_fd: int | None = None,
) -> SendStatus:
    """A child keeps the fence if its parent dies during the provider call."""
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    shared_fence = DupFd(fence_fd) if fence_fd is not None else None
    child = context.Process(
        target=_send, args=(provider, number, body, send, shared_fence, timeout_seconds)
    )
    try:
        child.start()
        send.close()
        if receive.poll(timeout_seconds):
            try:
                result = receive.recv()
            except (EOFError, OSError):
                result = "unknown"
        else:
            result = "unknown"
        child.join(timeout=0.1)
        if child.is_alive():
            child.terminate()
            child.join(timeout=1)
        return cast(
            SendStatus, result if result in ("accepted", "failed", "unknown") else "unknown"
        )
    except (OSError, RuntimeError, TypeError):
        return "unknown"
    finally:
        send.close()
        receive.close()


def _connection(provider: MessagingProvider, output: Connection, timeout_seconds: float) -> None:
    try:
        signal.signal(signal.SIGALRM, _timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        output.send(provider.connection())
    except Exception:
        try:
            output.send(None)
        except (BrokenPipeError, OSError):
            pass
    finally:
        output.close()


def bounded_connection(provider: MessagingProvider, *, timeout_seconds: float) -> object:
    """A connection probe is bounded too, before any business row is locked."""
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    child = context.Process(target=_connection, args=(provider, send, timeout_seconds))
    try:
        child.start()
        send.close()
        if receive.poll(timeout_seconds):
            try:
                result = receive.recv()
            except (EOFError, OSError):
                result = None
        else:
            result = None
        child.join(timeout=0.1)
        if child.is_alive():
            child.terminate()
            child.join(timeout=1)
        return result
    except (OSError, RuntimeError, TypeError):
        return None
    finally:
        send.close()
        receive.close()
