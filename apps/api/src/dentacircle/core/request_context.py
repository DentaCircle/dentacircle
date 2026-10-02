"""Request id header and one log line per request.

Unhandled errors are turned into the standard JSON body here, inside the middleware,
so the response still carries X-Request-ID. Starlette's outermost error middleware would
otherwise send that response without our header.
"""

import logging
import time
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from dentacircle.core.request_id import REQUEST_ID_SCOPE_KEY

_request_logger = logging.getLogger("dentacircle.request")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        scope[REQUEST_ID_SCOPE_KEY] = request_id
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if response_started:
                raise
            # Local import avoids a cycle: error handlers call current_request_id.
            from dentacircle.core.errors import unhandled_error_response

            response = unhandled_error_response(request_id, exc)
            await response(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000)
            _request_logger.info(
                "request_id=%s method=%s path=%s status=%s duration_ms=%s",
                request_id,
                scope["method"],
                scope["path"],
                status_code,
                duration_ms,
            )
