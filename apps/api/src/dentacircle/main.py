"""API application factory.

`app` builds the FastAPI instance on first use so importing this module does not
require DATABASE_URL. Uvicorn loads `dentacircle.main:app`.
"""

from fastapi import FastAPI
from starlette.types import Receive, Scope, Send

from dentacircle.api.auth import router as auth_router
from dentacircle.api.health import router as health_router
from dentacircle.core.config import get_settings
from dentacircle.core.errors import register_exception_handlers
from dentacircle.core.logging import configure_logging
from dentacircle.core.request_context import RequestContextMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    application = FastAPI()
    register_exception_handlers(application)
    application.add_middleware(RequestContextMiddleware)
    application.include_router(health_router)
    application.include_router(auth_router)
    return application


class _ASGIApp:
    def __init__(self) -> None:
        self._application: FastAPI | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._application is None:
            self._application = create_app()
        await self._application(scope, receive, send)


app = _ASGIApp()
