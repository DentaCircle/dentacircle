"""Migration preserves staff attribution and adds message-based actors."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from dentacircle.core.database import to_sqlalchemy_url


def test_action_actor_and_dispatch_schema(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(to_sqlalchemy_url(throwaway_database_url))
    try:
        inspector = inspect(engine)
        for table in ("audit_event", "timeline_event"):
            columns = {column["name"]: column for column in inspector.get_columns(table)}
            assert {"actor_kind", "actor_message_id"} <= columns.keys()
            assert columns["actor_user_id"]["nullable"]
            assert any(
                fk["referred_table"] == "message"
                and set(fk["constrained_columns"]) == {"actor_message_id", "clinic_id"}
                for fk in inspector.get_foreign_keys(table)
            )
        message_columns = {column["name"] for column in inspector.get_columns("message")}
        assert {
            "origin",
            "caused_by_message_id",
            "dispatch_order",
            "dispatch_owner",
            "dispatch_deadline_at",
        } <= message_columns
    finally:
        engine.dispose()


def test_existing_staff_rows_and_message_provenance_are_preserved(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import uuid4

    from sqlalchemy import text

    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0021_messaging")
    engine = create_engine(to_sqlalchemy_url(throwaway_database_url))
    clinic, user, patient, contact, incoming, outgoing, audit, timeline = [
        uuid4() for _ in range(8)
    ]
    params = dict(
        clinic=clinic,
        user=user,
        patient=patient,
        contact=contact,
        incoming=incoming,
        outgoing=outgoing,
        audit=audit,
        timeline=timeline,
        request=uuid4(),
    )
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO clinic (id, name) VALUES (:clinic, 'Synthetic clinic')"), params
            )
            conn.execute(
                text(
                    "INSERT INTO app_user (id, clinic_id, email, full_name, password_hash) "
                    "VALUES (:user, :clinic, 'sample@example.test', 'Sample', 'hash')"
                ),
                params,
            )
            conn.execute(
                text(
                    "INSERT INTO patient (id, clinic_id, patient_number, full_name, "
                    "phone, phone_digits) "
                    "VALUES (:patient, :clinic, 1, 'Sample', '9000000001', '9000000001')"
                ),
                params,
            )
            conn.execute(
                text(
                    "INSERT INTO messaging_contact (id, clinic_id, patient_id, "
                    "account_key, number, created_by_user_id) "
                    "VALUES (:contact, :clinic, :patient, 'demo', '+15551234567', :user)"
                ),
                params,
            )
            conn.execute(
                text(
                    "INSERT INTO message (id, clinic_id, contact_id, account_key, "
                    "direction, body, state, provider_message_id) "
                    "VALUES (:incoming, :clinic, :contact, 'demo', 'inbound', "
                    "'Hello', 'received', 'provider-id')"
                ),
                params,
            )
            conn.execute(
                text(
                    "INSERT INTO message (id, clinic_id, contact_id, account_key, "
                    "direction, body, state, created_by_user_id, request_id) "
                    "VALUES (:outgoing, :clinic, :contact, 'demo', 'outbound', "
                    "'Hello', 'accepted', :user, :request)"
                ),
                params,
            )
            conn.execute(
                text(
                    "INSERT INTO audit_event (id, clinic_id, actor_user_id, "
                    "entity_type, entity_id, action) "
                    "VALUES (:audit, :clinic, :user, 'patient', :patient, 'create')"
                ),
                params,
            )
            conn.execute(
                text(
                    "INSERT INTO timeline_event (id, clinic_id, patient_id, actor_user_id, kind) "
                    "VALUES (:timeline, :clinic, :patient, :user, 'patient_registered')"
                ),
                params,
            )
        command.upgrade(config, "head")
        with engine.connect() as conn:
            assert (
                conn.execute(
                    text("SELECT origin FROM message WHERE id = :incoming"), params
                ).scalar_one()
                == "provider"
            )
            assert (
                conn.execute(
                    text("SELECT origin FROM message WHERE id = :outgoing"), params
                ).scalar_one()
                == "staff"
            )
            for table, key in (("audit_event", "audit"), ("timeline_event", "timeline")):
                row = conn.execute(
                    text(
                        "SELECT actor_kind, actor_user_id, actor_message_id "
                        f"FROM {table} WHERE id = :id"
                    ),
                    {"id": params[key]},
                ).one()
                assert tuple(row) == ("staff", user, None)
        command.downgrade(config, "0021_messaging")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM message")).scalar_one() == 2
    finally:
        engine.dispose()
