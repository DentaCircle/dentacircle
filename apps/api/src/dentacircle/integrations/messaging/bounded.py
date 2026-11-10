"""Bound a provider call while retaining the caller's process fence."""

import multiprocessing
import os
import signal
from multiprocessing.connection import Connection
from multiprocessing.reduction import DupFd
from typing import Any, cast

from dentacircle.integrations.messaging.base import MessagingProvider, SendReceipt, SendStatus


def _timeout(_signal: int, _frame: object) -> None:
    raise TimeoutError


def _send(
    provider: MessagingProvider,
    number: str,
    body: str,
    output: Connection,
    shared_fence: Any,
    timeout_seconds: float,
    include_receipt: bool,
) -> None:
    fence_fd: int | None = None
    try:
        if shared_fence is not None:
            fence_fd = shared_fence.detach()
        signal.signal(signal.SIGALRM, _timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        connection = provider.connection()
        if connection.status == "connected" and connection.can_send_text:
            receipt_method = getattr(provider, "send_text_receipt", None)
            result = (
                receipt_method(number, body)
                if include_receipt and callable(receipt_method)
                else provider.send_text(number, body)
            )
        else:
            result = "failed"
        if isinstance(result, SendReceipt):
            output.send(result if include_receipt else result.status)
        else:
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


def _bounded_send(
    provider: MessagingProvider,
    number: str,
    body: str,
    *,
    timeout_seconds: float,
    fence_fd: int | None = None,
    include_receipt: bool = False,
) -> SendStatus | SendReceipt:
    """A child keeps the fence if its parent dies during the provider call."""
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    shared_fence = DupFd(fence_fd) if fence_fd is not None else None
    child = context.Process(
        target=_send,
        args=(provider, number, body, send, shared_fence, timeout_seconds, include_receipt),
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
        if child.is_alive():
            child.kill()
            child.join()
        if child.exitcode != 0 and shared_fence is not None:
            _release_unclaimed_fence(shared_fence)
        if include_receipt and isinstance(result, SendReceipt):
            return result
        return cast(
            SendStatus, result if result in ("accepted", "failed", "unknown") else "unknown"
        )
    except (OSError, RuntimeError, TypeError):
        if shared_fence is not None:
            _release_unclaimed_fence(shared_fence)
        return "unknown"
    finally:
        send.close()
        receive.close()


def _release_unclaimed_fence(shared_fence: Any) -> None:
    """Close the resource-sharer duplicate when startup failed before child detach."""
    try:
        duplicate_fd = shared_fence.detach()
    except (EOFError, KeyError, OSError):
        # The child already detached it; once joined, its process exit closes the fd.
        return
    os.close(duplicate_fd)


def bounded_send(
    provider: MessagingProvider,
    number: str,
    body: str,
    *,
    timeout_seconds: float,
    fence_fd: int | None = None,
) -> SendStatus:
    return cast(
        SendStatus,
        _bounded_send(provider, number, body, timeout_seconds=timeout_seconds, fence_fd=fence_fd),
    )


def bounded_send_receipt(
    provider: MessagingProvider,
    number: str,
    body: str,
    *,
    timeout_seconds: float,
    fence_fd: int | None = None,
) -> SendReceipt:
    result = _bounded_send(
        provider,
        number,
        body,
        timeout_seconds=timeout_seconds,
        fence_fd=fence_fd,
        include_receipt=True,
    )
    return result if isinstance(result, SendReceipt) else SendReceipt(result)


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
        if child.is_alive():
            child.kill()
            child.join()
        return result
    except (OSError, RuntimeError, TypeError):
        return None
    finally:
        send.close()
        receive.close()
