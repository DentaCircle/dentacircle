"""Contact and send rules run before any provider dispatch."""

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.integrations.messaging.base import Connection, IncomingText, SendStatus
from dentacircle.services.messaging_service import ContactConflict, link_contact, send_message
from tests.timeline_support import world

pytest_plugins = ["tests.timeline_support"]


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def connection(self) -> Connection:
        return Connection("connected", True)

    def send_text(self, number: str, body: str) -> SendStatus:
        self.calls.append((number, body))
        return "accepted"

    def normalize_event(self, payload: object) -> IncomingText | None:
        return None


def test_link_and_request_replay(database: str) -> None:
    clinic = world()
    provider = FakeProvider()
    request_id = uuid4()
    with Session(get_engine(), expire_on_commit=False) as session:
        first = link_contact(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "demo",
            "+15551234567",
            {"+15551234567"},
        )
        again = link_contact(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "demo",
            "+15551234567",
            {"+15551234567"},
        )
        assert first.id == again.id
        with pytest.raises(ContactConflict):
            link_contact(
                session,
                clinic.clinic_id,
                clinic.actor_id,
                clinic.patient_id,
                "demo",
                "+15557654321",
                {"+15557654321"},
            )
        message, created = send_message(
            session,
            provider,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            " Hello ",
            request_id,
            "demo",
            {"+15551234567"},
        )
        replay, created_again = send_message(
            session,
            provider,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "Hello",
            request_id,
            "demo",
            {"+15551234567"},
        )
        assert created and not created_again
        assert message.id == replay.id
        assert replay.state == "accepted"
        assert provider.calls == [("+15551234567", "Hello")]
        with pytest.raises(ContactConflict):
            send_message(
                session,
                provider,
                clinic.clinic_id,
                clinic.actor_id,
                clinic.patient_id,
                "different",
                request_id,
                "demo",
                {"+15551234567"},
            )


def test_incoming_is_deduplicated_and_unknown_is_ignored(database: str) -> None:
    from sqlalchemy import func, select

    from dentacircle.models.messaging import Message
    from dentacircle.services.messaging_service import receive_message

    clinic = world()
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "demo",
            "+15551234567",
            {"+15551234567"},
        )
        incoming = IncomingText("demo", "+15551234567", "provider-1", "Hello", None)
        receive_message(session, clinic.clinic_id, incoming)
        receive_message(session, clinic.clinic_id, incoming)
        receive_message(
            session,
            clinic.clinic_id,
            IncomingText("demo", "+15557654321", "provider-2", "Hi", None),
        )
        assert session.scalar(select(func.count()).select_from(Message)) == 1
        row = session.scalar(select(Message))
        assert row is not None and row.state == "received" and row.created_by_user_id is None


def test_attempt_and_audit_exist_before_dispatch_and_state_is_audited(database: str) -> None:
    from sqlalchemy import select

    from dentacircle.models.audit_event import AuditEvent
    from dentacircle.models.messaging import Message

    clinic = world()

    class InspectProvider(FakeProvider):
        def send_text(self, number: str, body: str) -> SendStatus:
            with Session(get_engine()) as other:
                row = other.scalar(select(Message).where(Message.clinic_id == clinic.clinic_id))
                assert row is not None and row.state == "sending"
                audit = other.scalar(select(AuditEvent).where(AuditEvent.entity_id == row.id))
                assert audit is not None and audit.action == "create"
            return "unknown"

    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "demo",
            "+15551234567",
            {"+15551234567"},
        )
        row, _ = send_message(
            session,
            InspectProvider(),
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "Hello",
            uuid4(),
            "demo",
            {"+15551234567"},
        )
        assert row.state == "unknown"
        audits = list(
            session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_id == row.id)
                .order_by(AuditEvent.occurred_at)
            )
        )
        assert [audit.action for audit in audits] == ["create", "status_change"]
        assert audits[1].actor_user_id == clinic.actor_id
        assert audits[1].changed_fields == ["state"]


def test_incoming_does_not_change_timeline_and_inactive_history_remains(database: str) -> None:
    from dentacircle.models.patient import Patient
    from dentacircle.services.messaging_service import receive_message
    from tests.timeline_support import kinds

    clinic = world()
    before = kinds(clinic.clinic_id, clinic.patient_id)
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "demo",
            "+15551234567",
            {"+15551234567"},
        )
        patient = session.get(Patient, clinic.patient_id)
        assert patient is not None
        patient.status = "inactive"
        session.commit()
        receive_message(
            session,
            clinic.clinic_id,
            IncomingText("demo", "+15551234567", "incoming", "Hello", None),
        )
        with pytest.raises(ContactConflict):
            send_message(
                session,
                FakeProvider(),
                clinic.clinic_id,
                clinic.actor_id,
                clinic.patient_id,
                "Hello",
                uuid4(),
                "demo",
                {"+15551234567"},
            )
    assert kinds(clinic.clinic_id, clinic.patient_id) == before


def test_concurrent_replay_dispatches_once(database: str) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock

    clinic = world()
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "demo",
            "+15551234567",
            {"+15551234567"},
        )
    barrier = Barrier(2)
    lock = Lock()
    provider = FakeProvider()

    class ConcurrentProvider(FakeProvider):
        def send_text(self, number: str, body: str) -> SendStatus:
            with lock:
                provider.calls.append((number, body))
            return "accepted"

    concurrent_provider = ConcurrentProvider()
    request_id = uuid4()

    def submit() -> tuple[object, bool]:
        with Session(get_engine(), expire_on_commit=False) as session:
            barrier.wait(timeout=10)
            row, created = send_message(
                session,
                concurrent_provider,
                clinic.clinic_id,
                clinic.actor_id,
                clinic.patient_id,
                "Hello",
                request_id,
                "demo",
                {"+15551234567"},
            )
            return row.id, created

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert results[0][0] == results[1][0]
    assert sorted(created for _, created in results) == [False, True]
    assert len(provider.calls) == 1


def test_concurrent_callback_deduplicates_before_acknowledgement(database: str) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import func, select

    from dentacircle.models.messaging import Message
    from dentacircle.services.messaging_service import receive_message

    clinic = world()
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "demo",
            "+15551234567",
            {"+15551234567"},
        )
    event = IncomingText("demo", "+15551234567", "provider-1", "Hello", None)
    barrier = Barrier(2)

    def deliver() -> None:
        with Session(get_engine()) as session:
            barrier.wait(timeout=10)
            receive_message(session, clinic.clinic_id, event)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: deliver(), range(2)))
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 1


def test_finalization_failure_does_not_redispatch(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    clinic = world()
    provider = FakeProvider()
    request_id = uuid4()
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "demo",
            "+15551234567",
            {"+15551234567"},
        )
        real_commit = session.commit
        commits = 0

        def fail_second_commit() -> None:
            nonlocal commits
            commits += 1
            if commits == 2:
                raise SQLAlchemyError("synthetic failure")
            real_commit()

        monkeypatch.setattr(session, "commit", fail_second_commit)
        with pytest.raises(SQLAlchemyError):
            send_message(
                session,
                provider,
                clinic.clinic_id,
                clinic.actor_id,
                clinic.patient_id,
                "Hello",
                request_id,
                "demo",
                {"+15551234567"},
            )
    with Session(get_engine(), expire_on_commit=False) as session:
        replay, created = send_message(
            session,
            provider,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "Hello",
            request_id,
            "demo",
            {"+15551234567"},
        )
        assert not created and replay.state == "sending"
    assert len(provider.calls) == 1


def test_failed_attempt_commit_does_not_dispatch(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import func, select
    from sqlalchemy.exc import SQLAlchemyError

    from dentacircle.models.messaging import Message

    clinic = world()
    provider = FakeProvider()
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "demo",
            "+15551234567",
            {"+15551234567"},
        )

        def fail_commit() -> None:
            raise SQLAlchemyError("synthetic failure")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(SQLAlchemyError):
            send_message(
                session,
                provider,
                clinic.clinic_id,
                clinic.actor_id,
                clinic.patient_id,
                "Hello",
                uuid4(),
                "demo",
                {"+15551234567"},
            )
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 0
    assert provider.calls == []
