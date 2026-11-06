"""Resume queued automatic replies inside the local API process."""

import logging
import threading
import time
from uuid import UUID

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from dentacircle.integrations.messaging.base import MessagingProvider
from dentacircle.repositories.automatic_dispatch_repository import AutomaticDispatchRepository
from dentacircle.services.automatic_dispatch import Guard, dispatch_one

_logger = logging.getLogger(__name__)


class Dispatcher:
    def __init__(
        self,
        engine: Engine,
        provider: MessagingProvider,
        clinic_id: UUID,
        account: str,
        allowlist: set[str],
        interval: float = 1.0,
        guard: Guard | None = None,
    ) -> None:
        self.engine = engine
        self.provider = provider
        self.clinic_id = clinic_id
        self.account = account
        self.allowlist = allowlist
        self.interval = interval
        self.guard = guard
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.active: dict[UUID, threading.Thread] = {}
        self.reported_busy: set[UUID] = set()
        self.cursor = 0
        self.thread = threading.Thread(target=self._run, name="automatic-dispatch", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)
        with self.lock:
            workers = list(self.active.values())
        deadline = time.monotonic() + 12
        for worker in workers:
            worker.join(timeout=max(0, deadline - time.monotonic()))

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                with Session(self.engine) as session:
                    contacts = AutomaticDispatchRepository(
                        session, self.clinic_id
                    ).pending_contacts()
                if contacts:
                    offset = self.cursor % len(contacts)
                    contacts = contacts[offset:] + contacts[:offset]
                    self.cursor = (offset + 16) % len(contacts)
                for contact_id in contacts:
                    with self.lock:
                        if contact_id in self.active or len(self.active) >= 16:
                            continue
                        worker = threading.Thread(target=self._one, args=(contact_id,), daemon=True)
                        self.active[contact_id] = worker
                        worker.start()
            except Exception as exc:
                _logger.warning("automatic dispatch scan failed: %s", type(exc).__name__)
            self.stop_event.wait(self.interval)

    def _one(self, contact_id: UUID) -> None:
        try:
            result = dispatch_one(
                self.engine,
                self.provider,
                self.clinic_id,
                contact_id,
                self.account,
                self.allowlist,
                self.guard,
            )
            with self.lock:
                if result == "busy" and contact_id not in self.reported_busy:
                    _logger.warning("automatic dispatch contact fence remains held")
                    self.reported_busy.add(contact_id)
                elif result != "busy":
                    self.reported_busy.discard(contact_id)
        except Exception as exc:
            _logger.warning("automatic dispatch failed: %s", type(exc).__name__)
        finally:
            with self.lock:
                self.active.pop(contact_id, None)
