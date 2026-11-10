"""API application factory.

`app` builds the FastAPI instance on first use so importing this module does not
require DATABASE_URL. Uvicorn loads `dentacircle.main:app`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI
from starlette.types import Receive, Scope, Send

from dentacircle.api.appointment_types import router as appointment_types_router
from dentacircle.api.appointments import router as appointments_router
from dentacircle.api.auth import router as auth_router
from dentacircle.api.care import router as care_router
from dentacircle.api.care_sessions import router as care_sessions_router
from dentacircle.api.clinic_day import router as clinic_day_router
from dentacircle.api.clinicians import router as clinicians_router
from dentacircle.api.documents import router as documents_router
from dentacircle.api.follow_ups import router as follow_ups_router
from dentacircle.api.health import router as health_router
from dentacircle.api.inventory import router as inventory_router
from dentacircle.api.lab_work import router as lab_work_router
from dentacircle.api.messaging import router as messaging_router
from dentacircle.api.patients import router as patients_router
from dentacircle.api.recalls import router as recalls_router
from dentacircle.api.reminders import router as reminders_router
from dentacircle.api.resource_rules import router as resource_rules_router
from dentacircle.api.timeline import router as timeline_router
from dentacircle.core.config import get_settings
from dentacircle.core.database import get_engine
from dentacircle.core.errors import register_exception_handlers
from dentacircle.core.logging import configure_logging
from dentacircle.core.request_context import RequestContextMiddleware
from dentacircle.integrations.messaging.openwa import OpenWaMessagingProvider
from dentacircle.services.automatic_dispatch_runtime import Dispatcher
from dentacircle.services.whatsapp_booking_service import render_queued_reply


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        dispatcher: Dispatcher | None = None
        allowlist = {
            number.strip() for number in settings.messaging_allowlist.split(",") if number.strip()
        }
        if (
            settings.messaging_url
            and settings.messaging_api_key
            and settings.messaging_account
            and settings.messaging_callback_secret
            and settings.messaging_clinic_id
            and allowlist
        ):
            try:
                clinic_id = UUID(settings.messaging_clinic_id)
            except ValueError:
                clinic_id = None
            if clinic_id is not None:
                provider = OpenWaMessagingProvider(
                    settings.messaging_url, settings.messaging_api_key, settings.messaging_account
                )
                dispatcher = Dispatcher(
                    get_engine(),
                    provider,
                    clinic_id,
                    settings.messaging_account,
                    allowlist,
                    guard=render_queued_reply,
                )
                dispatcher.start()
        try:
            yield
        finally:
            if dispatcher is not None:
                dispatcher.stop()

    application = FastAPI(lifespan=lifespan)
    register_exception_handlers(application)
    application.add_middleware(RequestContextMiddleware)
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(clinic_day_router)
    application.include_router(appointment_types_router)
    application.include_router(patients_router)
    application.include_router(clinicians_router)
    application.include_router(appointments_router)
    application.include_router(care_router)
    application.include_router(care_sessions_router)
    application.include_router(follow_ups_router)
    application.include_router(recalls_router)
    application.include_router(reminders_router)
    application.include_router(timeline_router)
    application.include_router(documents_router)
    application.include_router(lab_work_router)
    application.include_router(messaging_router)
    application.include_router(inventory_router)
    application.include_router(resource_rules_router)
    return application


class _ASGIApp:
    def __init__(self) -> None:
        self._application: FastAPI | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._application is None:
            self._application = create_app()
        await self._application(scope, receive, send)


app = _ASGIApp()
