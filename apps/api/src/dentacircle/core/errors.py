"""One JSON shape for every error response."""

import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request

from dentacircle.core.request_id import current_request_id

GENERIC_ERROR_MESSAGE = "Something went wrong."

_STATUS_CODES = {
    400: "bad_request",
    404: "not_found",
    405: "method_not_allowed",
    422: "validation_error",
    503: "service_unavailable",
}


def code_for_status(status_code: int) -> str:
    return _STATUS_CODES.get(status_code, "http_error")


def error_response(status_code: int, code: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
    )


def unhandled_error_response(request_id: str, exc: Exception) -> JSONResponse:
    """Log the exception class only. The traceback is logged at DEBUG, for local work."""
    logger = logging.getLogger("dentacircle.errors")
    logger.error("unhandled exception_class=%s request_id=%s", type(exc).__name__, request_id)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("traceback request_id=%s", request_id, exc_info=exc)
    return error_response(500, "internal_error", GENERIC_ERROR_MESSAGE, request_id)


def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        return unhandled_error_response(current_request_id(request), exc)
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    request_id = current_request_id(request)
    return error_response(exc.status_code, code_for_status(exc.status_code), message, request_id)


def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        return unhandled_error_response(current_request_id(request), exc)
    # `msg` and `input` can repeat the submitted value. Locations and rule names do not.
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        parts.append(f"{location}: {error['type']}")
    message = "; ".join(parts)
    return error_response(422, "validation_error", message, current_request_id(request))


def register_exception_handlers(application: FastAPI) -> None:
    application.add_exception_handler(HTTPException, handle_http_exception)
    application.add_exception_handler(RequestValidationError, handle_validation_error)
