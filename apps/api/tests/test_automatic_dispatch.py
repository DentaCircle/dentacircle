"""Automatic replies are claimed in order and never retried after a crash."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.integrations.messaging.base import Connection, IncomingText, SendStatus
from dentacircle.integrations.messaging.contact_fence import contact_fence
from dentacircle.models.messaging import Message
from dentacircle.services.automatic_dispatch import dispatch_one
from dentacircle.services.automatic_reply_service import queue_reply
from dentacircle.services.messaging_service import link_contact, receive_message
from dentacircle.services.whatsapp_actor import resolve_actor
from tests.test_whatsapp_actor import authority
from tests.timeline_support import world

pytest_plugins = ["tests.timeline_support"]
NUMBER = "+15551234567"


class Provider:
    def connection(self) -> Connection:
        return Connection("connected", True)

    def send_text(self, number: str, body: str, *, fence_fd: int | None = None) -> SendStatus:
        return "accepted"

    def normalize_event(self, payload: object) -> IncomingText | None:
        return None


def prepare() -> tuple[UUID, UUID, list[UUID]]:
    clinic = world()
    replies: list[UUID] = []
    with Session(get_engine(), expire_on_commit=False) as session:
        contact = link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", NUMBER, {NUMBER}
        )
        for index in range(2):
            receive_message(
                session,
                clinic.clinic_id,
                IncomingText("demo", NUMBER, f"incoming-{index}", "BOOK", None),
            )
            incoming = session.scalar(
                select(Message).where(
                    Message.clinic_id == clinic.clinic_id,
                    Message.provider_message_id == f"incoming-{index}",
                )
            )
            assert incoming is not None
            actor = resolve_actor(session, authority(clinic.clinic_id), incoming.id)
            reply = queue_reply(session, actor, f"reply-{index}")
            replies.append(reply.id)
            session.commit()
        return clinic.clinic_id, contact.id, replies


def states(session: Session, ids: list[UUID]) -> list[str]:
    rows = [session.get(Message, item_id) for item_id in ids]
    assert all(row is not None for row in rows)
    return [row.state for row in rows if row is not None]


def test_dispatch_in_order_and_never_redeliver(database: str) -> None:
    clinic, contact, ids = prepare()
    assert dispatch_one(get_engine(), Provider(), clinic, contact, "demo", {NUMBER}) == "sent"
    with Session(get_engine()) as session:
        assert states(session, ids) == ["accepted", "queued"]
    assert dispatch_one(get_engine(), Provider(), clinic, contact, "demo", {NUMBER}) == "sent"
    assert dispatch_one(get_engine(), Provider(), clinic, contact, "demo", {NUMBER}) == "idle"


def test_live_owner_fence_blocks_recovery_then_abandoned_claim_advances(database: str) -> None:
    clinic, contact, ids = prepare()
    with Session(get_engine()) as session:
        first = session.get(Message, ids[0])
        assert first is not None
        first.state = "sending"
        first.dispatch_owner = uuid4()
        first.dispatch_deadline_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
    with contact_fence(clinic, contact) as fence:
        assert fence is not None
        assert dispatch_one(get_engine(), Provider(), clinic, contact, "demo", {NUMBER}) == "busy"
        with Session(get_engine()) as session:
            assert states(session, ids)[0] == "sending"
    assert dispatch_one(get_engine(), Provider(), clinic, contact, "demo", {NUMBER}) == "sent"
    with Session(get_engine()) as session:
        assert states(session, ids) == ["unknown", "accepted"]


def test_ineligible_queued_reply_is_superseded(database: str) -> None:
    clinic, contact, ids = prepare()
    assert dispatch_one(get_engine(), Provider(), clinic, contact, "demo", set()) == "superseded"
    with Session(get_engine()) as session:
        assert states(session, ids) == ["superseded", "queued"]


def test_runtime_resumes_queued_replies(database: str) -> None:
    import time

    from dentacircle.services.automatic_dispatch_runtime import Dispatcher

    clinic, contact, ids = prepare()
    dispatcher = Dispatcher(get_engine(), Provider(), clinic, "demo", {NUMBER}, interval=0.05)
    dispatcher.start()
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            with Session(get_engine()) as session:
                current = states(session, ids)
            if current == ["accepted", "accepted"]:
                break
            time.sleep(0.05)
        assert current == ["accepted", "accepted"]
    finally:
        dispatcher.stop()


class HangingProvider(Provider):
    def __init__(self, marker: str) -> None:
        self.marker = marker

    def send_text(self, number: str, body: str, *, fence_fd: int | None = None) -> SendStatus:
        import time
        from pathlib import Path

        Path(self.marker).touch()
        time.sleep(30)
        return "accepted"


def _dispatch_in_process(database_url: str, clinic: UUID, contact: UUID, marker: str) -> None:
    from sqlalchemy import create_engine

    from dentacircle.core.database import to_sqlalchemy_url
    from dentacircle.services import automatic_dispatch

    automatic_dispatch._SEND_SECONDS = 3
    engine = create_engine(to_sqlalchemy_url(database_url))
    dispatch_one(engine, HangingProvider(marker), clinic, contact, "demo", {NUMBER})


def test_killed_owner_is_fenced_until_send_child_exits(database: str, tmp_path: object) -> None:
    import multiprocessing
    import time
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    clinic, contact, ids = prepare()
    marker = tmp_path / "sending"
    process = multiprocessing.get_context("spawn").Process(
        target=_dispatch_in_process, args=(database, clinic, contact, str(marker))
    )
    process.start()
    try:
        deadline = time.monotonic() + 8
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists()
        process.terminate()
        process.join(timeout=3)
        assert not process.is_alive()
        # The child still holds the same fence even though its dispatcher died.
        assert dispatch_one(get_engine(), Provider(), clinic, contact, "demo", {NUMBER}) == "busy"
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            with contact_fence(clinic, contact) as fd:
                if fd is not None:
                    break
            time.sleep(0.05)
        else:
            raise AssertionError("send child did not release its fence")
        assert dispatch_one(get_engine(), Provider(), clinic, contact, "demo", {NUMBER}) == "sent"
        with Session(get_engine()) as session:
            assert states(session, ids) == ["unknown", "accepted"]
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=3)


def test_claim_refreshes_queued_body_and_suppresses_obsolete_reply(database: str) -> None:
    clinic, contact, ids = prepare()
    seen: list[str] = []

    def refresh(_session: Session, row: Message) -> str | None:
        seen.append(row.state)
        return "Refreshed reply" if row.id == ids[0] else None

    assert (
        dispatch_one(get_engine(), Provider(), clinic, contact, "demo", {NUMBER}, refresh) == "sent"
    )
    assert (
        dispatch_one(get_engine(), Provider(), clinic, contact, "demo", {NUMBER}, refresh)
        == "superseded"
    )
    with Session(get_engine()) as session:
        first = session.get(Message, ids[0])
        second = session.get(Message, ids[1])
        assert first is not None and second is not None
        assert (first.body, first.state, second.state) == (
            "Refreshed reply",
            "accepted",
            "superseded",
        )
    assert seen == ["queued", "queued"]


def test_stale_owner_cannot_finalize_a_claim(
    database: str, tmp_path: object, monkeypatch: object
) -> None:
    import threading
    import time
    from pathlib import Path

    import pytest

    from dentacircle.models.messaging import MessagingContact
    from dentacircle.models.patient import Patient
    from dentacircle.services import automatic_dispatch

    assert isinstance(tmp_path, Path) and isinstance(monkeypatch, pytest.MonkeyPatch)
    monkeypatch.setattr(automatic_dispatch, "_SEND_SECONDS", 2.0)
    clinic, contact, ids = prepare()
    marker = tmp_path / "stale"
    result: list[str] = []
    thread = threading.Thread(
        target=lambda: result.append(
            dispatch_one(
                get_engine(), HangingProvider(str(marker)), clinic, contact, "demo", {NUMBER}
            )
        )
    )
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists()
        assert dispatch_one(get_engine(), Provider(), clinic, contact, "demo", {NUMBER}) == "busy"
        with Session(get_engine()) as session:
            linked = session.get(MessagingContact, contact)
            assert linked is not None
            # The provider call is in flight, but no patient row lock is held.
            patient = session.scalar(
                select(Patient).where(Patient.id == linked.patient_id).with_for_update(nowait=True)
            )
            assert patient is not None
            session.rollback()
        with Session(get_engine()) as session:
            row = session.get(Message, ids[0])
            assert row is not None and row.state == "sending"
            replacement = uuid4()
            row.dispatch_owner = replacement
            session.commit()
        thread.join(timeout=5)
        assert not thread.is_alive() and result == ["sent"]
        with Session(get_engine()) as session:
            row = session.get(Message, ids[0])
            assert row is not None and row.state == "sending" and row.dispatch_owner == replacement
    finally:
        thread.join(timeout=5)


def test_a_busy_contact_does_not_block_another_contact(database: str) -> None:
    from dentacircle.models.messaging import MessagingContact
    from dentacircle.services.patient_service import register_patient

    clinic, first_contact, _ids = prepare()
    second_number = "+15557654321"
    with Session(get_engine(), expire_on_commit=False) as session:
        first = session.get(MessagingContact, first_contact)
        assert first is not None
        second = register_patient(
            session, clinic, first.created_by_user_id, "Sample Other", "9000000002", None
        )
        session.commit()
        contact = link_contact(
            session,
            clinic,
            first.created_by_user_id,
            second.id,
            "demo",
            second_number,
            {second_number},
        )
        receive_message(
            session, clinic, IncomingText("demo", second_number, "second-contact", "BOOK", None)
        )
        inbound = session.scalar(
            select(Message).where(
                Message.clinic_id == clinic, Message.provider_message_id == "second-contact"
            )
        )
        assert inbound is not None
        actor = resolve_actor(session, authority(clinic, numbers=second_number), inbound.id)
        reply = queue_reply(session, actor, "Second contact reply")
        reply_id, contact_id = reply.id, contact.id
        session.commit()
    with contact_fence(clinic, first_contact) as first_fence:
        assert first_fence is not None
        assert (
            dispatch_one(get_engine(), Provider(), clinic, first_contact, "demo", {NUMBER})
            == "busy"
        )
        assert (
            dispatch_one(get_engine(), Provider(), clinic, contact_id, "demo", {second_number})
            == "sent"
        )
    with Session(get_engine()) as session:
        assert states(session, [reply_id]) == ["accepted"]


def test_staff_send_does_not_overlap_an_automatic_send(database: str) -> None:
    from dentacircle.models.messaging import MessagingContact
    from dentacircle.services.messaging_service import send_message
    from tests.test_messaging_service import FakeProvider

    clinic, contact_id, _ids = prepare()
    provider = FakeProvider()
    with Session(get_engine(), expire_on_commit=False) as session:
        contact = session.get(MessagingContact, contact_id)
        assert contact is not None
        with contact_fence(clinic, contact_id) as fence:
            assert fence is not None
            row, created = send_message(
                session,
                provider,
                clinic,
                contact.created_by_user_id,
                contact.patient_id,
                "Staff reply",
                uuid4(),
                "demo",
                {NUMBER},
            )
        assert created and row.state == "failed"
        assert provider.calls == []


def test_staff_provider_call_holds_no_patient_row_lock_and_serializes_deactivation(
    database: str,
) -> None:
    import threading
    import time

    from dentacircle.models.messaging import MessagingContact
    from dentacircle.models.patient import Patient
    from dentacircle.services.messaging_service import send_message
    from dentacircle.services.patient_service import set_patient_status

    clinic, contact_id, _ids = prepare()
    started, finish = threading.Event(), threading.Event()
    outcomes: list[str] = []

    class BlockingProvider(Provider):
        def send_text(self, number: str, body: str, *, fence_fd: int | None = None) -> SendStatus:
            started.set()
            assert finish.wait(timeout=8)
            return "accepted"

    with Session(get_engine()) as session:
        contact = session.get(MessagingContact, contact_id)
        assert contact is not None
        user_id, patient_id = contact.created_by_user_id, contact.patient_id

    def send() -> None:
        with Session(get_engine()) as session:
            row, _created = send_message(
                session,
                BlockingProvider(),
                clinic,
                user_id,
                patient_id,
                "Staff reply",
                uuid4(),
                "demo",
                {NUMBER},
            )
            outcomes.append(row.state)

    def deactivate() -> None:
        with Session(get_engine()) as session:
            set_patient_status(session, clinic, user_id, patient_id, "inactive")
            session.commit()
            outcomes.append("inactive")

    sender = threading.Thread(target=send)
    changer = threading.Thread(target=deactivate)
    sender.start()
    try:
        assert started.wait(timeout=5)
        with Session(get_engine()) as session:
            assert (
                session.scalar(
                    select(Patient).where(Patient.id == patient_id).with_for_update(nowait=True)
                )
                is not None
            )
            session.rollback()
        changer.start()
        time.sleep(0.2)
        assert changer.is_alive()
    finally:
        finish.set()
        sender.join(timeout=10)
        if changer.ident is not None:
            changer.join(timeout=10)
    assert not sender.is_alive() and not changer.is_alive()
    assert sorted(outcomes) == ["accepted", "inactive"]


def test_deactivated_patient_supersedes_queued_automatic_reply(database: str) -> None:
    from dentacircle.models.messaging import MessagingContact
    from dentacircle.services.patient_service import set_patient_status

    clinic, contact_id, ids = prepare()
    with Session(get_engine()) as session:
        contact = session.get(MessagingContact, contact_id)
        assert contact is not None
        set_patient_status(
            session, clinic, contact.created_by_user_id, contact.patient_id, "inactive"
        )
        session.commit()
    assert (
        dispatch_one(get_engine(), Provider(), clinic, contact_id, "demo", {NUMBER}) == "superseded"
    )
    with Session(get_engine()) as session:
        assert states(session, ids) == ["superseded", "queued"]


def test_automatic_send_serializes_deactivation_without_patient_row_lock(
    database: str, tmp_path: object, monkeypatch: object
) -> None:
    import threading
    import time
    from pathlib import Path

    import pytest

    from dentacircle.models.messaging import MessagingContact
    from dentacircle.models.patient import Patient
    from dentacircle.services import automatic_dispatch
    from dentacircle.services.patient_service import set_patient_status

    assert isinstance(tmp_path, Path) and isinstance(monkeypatch, pytest.MonkeyPatch)
    monkeypatch.setattr(automatic_dispatch, "_SEND_SECONDS", 2.0)
    clinic, contact_id, _ids = prepare()
    marker = tmp_path / "automatic-in-flight"
    with Session(get_engine()) as session:
        contact = session.get(MessagingContact, contact_id)
        assert contact is not None
        user_id, patient_id = contact.created_by_user_id, contact.patient_id

    def deactivate() -> None:
        with Session(get_engine()) as session:
            set_patient_status(session, clinic, user_id, patient_id, "inactive")
            session.commit()

    sender = threading.Thread(
        target=dispatch_one,
        args=(get_engine(), HangingProvider(str(marker)), clinic, contact_id, "demo", {NUMBER}),
    )
    changer = threading.Thread(target=deactivate)
    sender.start()
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists()
        with Session(get_engine()) as session:
            assert (
                session.scalar(
                    select(Patient).where(Patient.id == patient_id).with_for_update(nowait=True)
                )
                is not None
            )
            session.rollback()
        changer.start()
        time.sleep(0.2)
        assert changer.is_alive()
    finally:
        sender.join(timeout=5)
        if changer.ident is not None:
            changer.join(timeout=5)
    assert not sender.is_alive() and not changer.is_alive()
