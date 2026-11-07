"""Booking state is durable and belongs to the linked clinic."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from dentacircle.core.database import to_sqlalchemy_url


def test_booking_schema(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(to_sqlalchemy_url(throwaway_database_url))
    try:
        inspector = inspect(engine)
        contact = {col["name"] for col in inspector.get_columns("messaging_contact")}
        assert {"automation_state", "automation_version", "automation_changed_at"} <= contact
        message = {col["name"] for col in inspector.get_columns("message")}
        assert {
            "purpose",
            "booking_session_id",
            "menu_version",
            "automation_version",
            "reply_kind",
        } <= message
        booking = {col["name"] for col in inspector.get_columns("whatsapp_booking_session")}
        assert {
            "clinic_id",
            "contact_id",
            "account_key",
            "state",
            "menu_token",
            "menu_version",
            "automation_version",
            "choices",
            "acknowledged_visits",
            "expires_at",
            "booked_appointment_id",
        } <= booking
        foreign_keys = inspector.get_foreign_keys("whatsapp_booking_session")
        assert any(
            fk["referred_table"] == "messaging_contact"
            and set(fk["constrained_columns"]) == {"clinic_id", "contact_id", "account_key"}
            for fk in foreign_keys
        )
    finally:
        engine.dispose()


def test_existing_staff_messages_and_contact_are_backfilled(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import uuid4

    from sqlalchemy import text

    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0022_whatsapp_actions")
    engine = create_engine(to_sqlalchemy_url(throwaway_database_url))
    values = {
        key: uuid4() for key in ("clinic", "staff", "patient", "contact", "message", "request")
    }
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO clinic (id, name) VALUES (:clinic, 'Synthetic Clinic')"), values
            )
            conn.execute(
                text(
                    "INSERT INTO app_user (id, clinic_id, email, full_name, password_hash) "
                    "VALUES (:staff, :clinic, 'synthetic@example.test', 'Synthetic Staff', 'hash')"
                ),
                values,
            )
            conn.execute(
                text(
                    "INSERT INTO patient (id, clinic_id, patient_number, full_name, "
                    "phone, phone_digits) "
                    "VALUES (:patient, :clinic, 1, 'Synthetic Person', '9000000001', '9000000001')"
                ),
                values,
            )
            conn.execute(
                text(
                    "INSERT INTO messaging_contact (id, clinic_id, patient_id, account_key, "
                    "number, created_by_user_id) "
                    "VALUES (:contact, :clinic, :patient, 'demo', '+15551234567', :staff)"
                ),
                values,
            )
            conn.execute(
                text(
                    "INSERT INTO message (id, clinic_id, contact_id, account_key, "
                    "direction, origin, "
                    "body, state, created_by_user_id, request_id) "
                    "VALUES (:message, :clinic, :contact, 'demo', 'outbound', 'staff', "
                    "'Hello', 'accepted', :staff, :request)"
                ),
                values,
            )
        command.upgrade(config, "head")
        with engine.connect() as conn:
            contact = conn.execute(
                text(
                    "SELECT automation_state, automation_version, "
                    "automation_changed_at = created_at "
                    "FROM messaging_contact WHERE id = :contact"
                ),
                values,
            ).one()
            assert contact == ("active", 0, True)
            purpose = conn.scalar(text("SELECT purpose FROM message WHERE id = :message"), values)
            assert purpose == "chat"
    finally:
        engine.dispose()
