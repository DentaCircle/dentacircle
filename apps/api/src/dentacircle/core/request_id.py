"""Request id stored on the ASGI scope by the request middleware."""

from starlette.requests import Request

REQUEST_ID_SCOPE_KEY = "dentacircle_request_id"


def current_request_id(request: Request) -> str:
    return str(request.scope.get(REQUEST_ID_SCOPE_KEY, ""))
