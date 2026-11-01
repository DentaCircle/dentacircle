"""Messaging endpoints enforce staff roles and callback credentials."""

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.models.clinic import Clinic
from tests.patient_harness import login, patient_api


def test_routes_and_callback(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with patient_api(throwaway_database_url, monkeypatch) as api:
        with Session(get_engine()) as session:
            clinic = session.scalar(select(Clinic))
            assert clinic is not None
            monkeypatch.setenv("MESSAGING_CLINIC_ID", str(clinic.id))
        monkeypatch.setenv("MESSAGING_ACCOUNT", "demo")
        monkeypatch.setenv("MESSAGING_CALLBACK_SECRET", "synthetic-secret")
        monkeypatch.setenv("MESSAGING_ALLOWLIST", "+15551234567")
        desk = {"dc_session": login(api, "receptionist@x.test")}
        inventory = {"dc_session": login(api, "inventory@x.test")}
        api.cookies.clear()
        assert api.get("/messages").status_code == 401
        assert api.get("/messages", cookies=inventory).status_code == 403
        created = api.post(
            "/patients",
            cookies=desk,
            json={"full_name": "Synthetic Example", "phone": "9000000001"},
        )
        assert created.status_code == 201
        patient_id = created.json()["id"]
        linked = api.put(
            f"/patients/{patient_id}/messaging-contact",
            cookies=desk,
            json={"number": "+15551234567"},
        )
        assert linked.status_code == 200
        payload: dict[str, Any] = {
            "sessionId": "demo",
            "event": "onMessage",
            "data": {
                "id": "synthetic-id",
                "from": "15551234567@c.us",
                "body": "Hello",
                "type": "chat",
                "fromMe": False,
                "isGroupMsg": False,
            },
        }
        path = "/integrations/messaging/openwa/events"
        assert api.post(path, json=payload).status_code == 401
        assert (
            api.post(path, content="{", headers={"Content-Type": "application/json"}).status_code
            == 401
        )
        assert (
            api.post(path, headers={"X-Webhook-Secret": "wrong"}, json=payload).status_code == 401
        )
        assert (
            api.post(
                path, headers={"X-Webhook-Secret": "synthetic-secret"}, json=payload
            ).status_code
            == 204
        )
        assert (
            api.post(
                path, headers={"X-Webhook-Secret": "synthetic-secret"}, json=payload
            ).status_code
            == 204
        )
        malformed = api.post(
            path,
            headers={"X-Webhook-Secret": "synthetic-secret"},
            content="{",
        )
        assert malformed.status_code == 422
        payload["sessionId"] = "different"
        assert (
            api.post(
                path, headers={"X-Webhook-Secret": "synthetic-secret"}, json=payload
            ).status_code
            == 204
        )
        payload["sessionId"] = "demo"
        from sqlalchemy.exc import SQLAlchemyError

        from dentacircle.repositories.messaging_repository import MessagingRepository

        def fail_write(*args: object) -> None:
            raise SQLAlchemyError("provider data must not leak")

        monkeypatch.setattr(MessagingRepository, "add_incoming", fail_write)
        payload["data"]["id"] = "another-id"
        failed = api.post(path, headers={"X-Webhook-Secret": "synthetic-secret"}, json=payload)
        assert failed.status_code == 503
        assert "provider data must not leak" not in failed.text
        caplog.clear()
        history = api.get(f"/patients/{patient_id}/messages", cookies=desk)
        server_logs = " ".join(
            record.getMessage()
            for record in caplog.records
            if record.name.startswith("dentacircle")
        )
        assert patient_id not in server_logs
        assert "+15551234567" not in server_logs
        assert history.status_code == 200
        assert history.json()["total"] == 1
        assert history.json()["items"][0]["body"] == "Hello"
        listing = api.get("/messages", cookies=desk)
        assert listing.status_code == 200
        assert listing.json()["items"][0]["message_count"] == 1
        assert api.get(f"/patients/{uuid4()}/messages", cookies=desk).status_code == 404


def test_foreign_patient_is_not_found(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dentacircle.services.patient_service import register_patient
    from dentacircle.services.provisioning_service import create_user, get_or_create_clinic

    with patient_api(throwaway_database_url, monkeypatch) as api:
        with Session(get_engine()) as session:
            foreign = get_or_create_clinic(session, "Other Synthetic Clinic")
            actor = create_user(
                session,
                foreign.id,
                "other@example.test",
                "Other Staff",
                "synthetic-password-marker",
                ["receptionist"],
            )
            patient = register_patient(
                session, foreign.id, actor.id, "Other Synthetic", "9000000002", None
            )
            session.commit()
            foreign_id = str(patient.id)
        desk = {"dc_session": login(api, "receptionist@x.test")}
        assert api.get(f"/patients/{foreign_id}/messaging-contact", cookies=desk).status_code == 404
        assert api.get(f"/patients/{foreign_id}/messages", cookies=desk).status_code == 404
        assert (
            api.put(
                f"/patients/{foreign_id}/messaging-contact",
                cookies=desk,
                json={"number": "+15551234567"},
            ).status_code
            == 404
        )
        assert (
            api.post(
                f"/patients/{foreign_id}/messages",
                cookies=desk,
                json={"body": "Hello", "request_id": str(uuid4())},
            ).status_code
            == 404
        )
