"""Staff visit mutations wait for the patient before locking the visit."""

import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.models.appointment import Appointment
from dentacircle.models.patient import Patient
from dentacircle.services.appointment_service import (
    cancel_appointment,
    change_status,
    reschedule_appointment,
)
from tests.timeline_support import AT_START, NOW, book, later, world

pytest_plugins = ["tests.timeline_support"]


@pytest.mark.parametrize("action", ["cancel", "reschedule", "status"])
def test_staff_visit_write_locks_patient_before_visit(database: str, action: str) -> None:
    clinic = world()
    visit_id = book(clinic, AT_START)
    pid: Queue[int] = Queue()

    def mutate() -> None:
        with Session(get_engine()) as session:
            backend_pid = session.scalar(text("SELECT pg_backend_pid()"))
            assert backend_pid is not None
            pid.put(backend_pid)
            if action == "cancel":
                cancel_appointment(session, clinic.clinic_id, clinic.actor_id, visit_id, NOW)
            elif action == "reschedule":
                reschedule_appointment(
                    session, clinic.clinic_id, clinic.actor_id, visit_id, later(60), None, NOW
                )
            else:
                change_status(
                    session,
                    clinic.clinic_id,
                    clinic.actor_id,
                    ["clinician"],
                    visit_id,
                    "arrived",
                    AT_START,
                )
            session.commit()

    with Session(get_engine()) as patient_lock, ThreadPoolExecutor(max_workers=1) as pool:
        assert patient_lock.scalar(
            select(Patient).where(Patient.id == clinic.patient_id).with_for_update()
        )
        future = pool.submit(mutate)
        try:
            backend_pid = pid.get(timeout=5)
            with Session(get_engine()) as observer:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    waiting = observer.scalar(
                        text(
                            "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"
                        ),
                        {"pid": backend_pid},
                    )
                    if waiting:
                        break
                    time.sleep(0.02)
                else:
                    raise AssertionError("staff mutation did not wait for the patient lock")
                # The waiting writer must not hold the visit while blocked on the patient.
                assert (
                    observer.scalar(
                        select(Appointment)
                        .where(Appointment.id == visit_id)
                        .with_for_update(nowait=True)
                    )
                    is not None
                )
                observer.rollback()
        finally:
            patient_lock.rollback()
        future.result(timeout=10)
