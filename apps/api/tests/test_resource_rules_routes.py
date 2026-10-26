"""Resource rule routes: roles, check order, tenancy, audit, and no echo."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.inventory import INVENTORY_READ_ROLES, INVENTORY_WRITE_ROLES
from dentacircle.main import create_app
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.repositories.appointment_repository import AppointmentRepository
from tests.patient_harness import login, patient_api
from tests.test_access import iter_api_routes, unmarked_routes
from tests.test_timeline_routes import _route_roles

_MARKER = "distinctive-rule-marker"
_READ = {("GET", "/appointment-types/{type_id}/resource-rules")}
_WRITE = {
    ("PUT", "/appointment-types/{type_id}/resource-rules/{item_id}"),
    ("DELETE", "/appointment-types/{type_id}/resource-rules/{item_id}"),
}


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_a_rule_is_created_replaced_and_listed_by_item_name(api: TestClient) -> None:
    cookies = _cookie(api, "inventory@x.test")
    type_id = _type_id("Consultation")
    gloves = _item(api, cookies, "Gloves M")
    masks = _item(api, cookies, "Masks")
    empty = api.get(f"/appointment-types/{type_id}/resource-rules", cookies=cookies)
    assert empty.status_code == 200
    assert empty.json() == []
    created = api.put(
        f"/appointment-types/{type_id}/resource-rules/{masks}",
        cookies=cookies,
        json={"quantity": 1},
    )
    assert created.status_code == 200
    assert created.json() == {"item_id": masks, "item_name": "Masks", "quantity": 1}
    api.put(
        f"/appointment-types/{type_id}/resource-rules/{gloves}",
        cookies=cookies,
        json={"quantity": 2},
    )
    replaced = api.put(
        f"/appointment-types/{type_id}/resource-rules/{masks}",
        cookies=cookies,
        json={"quantity": 3},
    )
    assert replaced.status_code == 200
    assert replaced.json()["quantity"] == 3
    listed = api.get(f"/appointment-types/{type_id}/resource-rules", cookies=cookies)
    assert [(row["item_name"], row["quantity"]) for row in listed.json()] == [
        ("Gloves M", 2),
        ("Masks", 3),
    ]
    actions = [event.action for event in _audits()]
    assert actions == ["create", "create", "update"]
    assert _audits()[-1].changed_fields == ["quantity"]
    assert all("3" not in "".join(event.changed_fields or []) for event in _audits())


def test_checks_run_in_order(api: TestClient) -> None:
    missing = str(uuid4())
    anonymous = api.put(
        f"/appointment-types/{missing}/resource-rules/{missing}",
        json={"quantity": True},
    )
    assert anonymous.status_code == 401
    denied = api.put(
        f"/appointment-types/{missing}/resource-rules/{missing}",
        cookies=_cookie(api),
        json={"quantity": True},
    )
    assert denied.status_code == 403
    cookies = _cookie(api, "admin@x.test")
    invalid = api.put(
        f"/appointment-types/{missing}/resource-rules/{missing}",
        cookies=cookies,
        json={"quantity": True},
    )
    assert invalid.status_code == 422
    absent = api.put(
        f"/appointment-types/{missing}/resource-rules/{missing}",
        cookies=cookies,
        json={"quantity": 2},
    )
    assert absent.status_code == 404
    type_id = _type_id("Consultation")
    missing_item = api.put(
        f"/appointment-types/{type_id}/resource-rules/{missing}",
        cookies=cookies,
        json={"quantity": 2},
    )
    assert missing_item.status_code == 404
    item_id = _item(api, cookies, "Gloves M")
    api.post(f"/inventory/items/{item_id}/status", cookies=cookies, json={"status": "inactive"})
    inactive = api.put(
        f"/appointment-types/{type_id}/resource-rules/{item_id}",
        cookies=cookies,
        json={"quantity": 2},
    )
    assert inactive.status_code == 409
    assert inactive.json()["error"]["code"] == "item_inactive"


@pytest.mark.parametrize("quantity", [True, 1.5, "2", 0, 1001])
def test_a_quantity_must_be_a_whole_number_from_1_to_1000(
    api: TestClient, quantity: object
) -> None:
    cookies = _cookie(api, "inventory@x.test")
    type_id = _type_id("Scaling")
    item_id = _item(api, cookies)
    response = api.put(
        f"/appointment-types/{type_id}/resource-rules/{item_id}",
        cookies=cookies,
        json={"quantity": quantity},
    )
    assert response.status_code == 422
    assert "424242" not in response.text


def test_an_existing_rule_for_an_inactive_item_stays_until_it_is_removed(api: TestClient) -> None:
    cookies = _cookie(api, "admin@x.test")
    type_id = _type_id("Scaling")
    item_id = _item(api, cookies, "Gloves M")
    api.put(
        f"/appointment-types/{type_id}/resource-rules/{item_id}",
        cookies=cookies,
        json={"quantity": 2},
    )
    api.post(f"/inventory/items/{item_id}/status", cookies=cookies, json={"status": "inactive"})
    refused = api.put(
        f"/appointment-types/{type_id}/resource-rules/{item_id}",
        cookies=cookies,
        json={"quantity": 4},
    )
    assert refused.status_code == 409
    listed = api.get(f"/appointment-types/{type_id}/resource-rules", cookies=cookies)
    assert listed.json() == [{"item_id": item_id, "item_name": "Gloves M", "quantity": 2}]
    removed = api.delete(
        f"/appointment-types/{type_id}/resource-rules/{item_id}",
        cookies=cookies,
    )
    assert removed.status_code == 204
    assert removed.content == b""
    assert api.get(f"/appointment-types/{type_id}/resource-rules", cookies=cookies).json() == []
    missing = api.delete(
        f"/appointment-types/{type_id}/resource-rules/{item_id}",
        cookies=cookies,
    )
    assert missing.status_code == 404
    assert [event.action for event in _audits()] == ["create", "delete"]


def test_readers_and_writers(api: TestClient) -> None:
    cookies = _cookie(api, "inventory@x.test")
    type_id = _type_id("Consultation")
    item_id = _item(api, cookies)
    saved = api.put(
        f"/appointment-types/{type_id}/resource-rules/{item_id}",
        cookies=cookies,
        json={"quantity": 1},
    )
    assert saved.status_code == 200
    clinician = _cookie(api, "clinician@x.test")
    listed = api.get(f"/appointment-types/{type_id}/resource-rules", cookies=clinician)
    assert listed.status_code == 200
    refused = api.put(
        f"/appointment-types/{type_id}/resource-rules/{item_id}",
        cookies=clinician,
        json={"quantity": 2},
    )
    assert refused.status_code == 403
    desk = _cookie(api)
    assert api.get(f"/appointment-types/{type_id}/resource-rules", cookies=desk).status_code == 403
    assert (
        api.delete(
            f"/appointment-types/{type_id}/resource-rules/{item_id}",
            cookies=desk,
        ).status_code
        == 403
    )
    admin = _cookie(api, "admin@x.test")
    assert (
        api.delete(
            f"/appointment-types/{type_id}/resource-rules/{item_id}",
            cookies=admin,
        ).status_code
        == 204
    )


def test_another_clinic_learns_nothing(api: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    cookies = _cookie(api, "inventory@x.test")
    type_id = _type_id("Consultation")
    item_id = _item(api, cookies, _MARKER)
    api.put(
        f"/appointment-types/{type_id}/resource-rules/{item_id}",
        cookies=cookies,
        json={"quantity": 2},
    )
    _other_clinic()
    other = _cookie(api, "other@x.test")
    listed = api.get(f"/appointment-types/{type_id}/resource-rules", cookies=other)
    stolen = api.put(
        f"/appointment-types/{type_id}/resource-rules/{item_id}",
        cookies=other,
        json={"quantity": 2},
    )
    assert listed.status_code == 404
    assert stolen.status_code == 404
    assert _MARKER not in listed.text
    assert _MARKER not in stolen.text
    assert type_id not in listed.text
    assert item_id not in listed.text
    assert "424242" not in stolen.text
    log = "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith("dentacircle")
    )
    assert _MARKER not in log
    assert "424242" not in log


def test_completing_a_visit_writes_one_consumption_and_a_replay_writes_nothing(
    api: TestClient,
) -> None:
    cookies = _cookie(api, "inventory@x.test")
    type_id = _type_id("Consultation")
    item_id = _item(api, cookies, "Gloves M")
    batch = api.post(
        f"/inventory/items/{item_id}/batches",
        cookies=cookies,
        json={"batch_number": "LOT-1", "expiry_on": "2026-12-01"},
    )
    assert batch.status_code == 201
    added = api.post(
        f"/inventory/batches/{batch.json()['id']}/restock",
        cookies=cookies,
        json={"quantity": 5},
    )
    assert added.status_code == 201
    assert added.json()["appointment_id"] is None
    assert added.json()["visit_on"] is None
    rule = api.put(
        f"/appointment-types/{type_id}/resource-rules/{item_id}",
        cookies=cookies,
        json={"quantity": 2},
    )
    assert rule.status_code == 200
    visit_id = _visit(type_id)
    clinician = _cookie(api, "clinician@x.test")
    completed = api.post(
        f"/appointments/{visit_id}/status",
        cookies=clinician,
        json={"status": "completed"},
    )
    assert completed.status_code == 200
    history = api.get(f"/inventory/items/{item_id}/transactions", cookies=cookies)
    assert history.status_code == 200
    consumption = next(row for row in history.json()["items"] if row["type"] == "consumption")
    assert consumption["quantity_change"] == -2
    assert consumption["reason"] is None
    assert consumption["appointment_id"] == visit_id
    assert consumption["visit_on"] == "2026-10-26"
    detail = api.get(f"/inventory/items/{item_id}", cookies=cookies)
    assert detail.json()["stock"] == 3
    again = api.post(
        f"/appointments/{visit_id}/status",
        cookies=clinician,
        json={"status": "completed"},
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_status"
    replayed = api.get(f"/inventory/items/{item_id}/transactions", cookies=cookies)
    assert replayed.json()["total"] == history.json()["total"]
    assert sum(1 for row in replayed.json()["items"] if row["type"] == "consumption") == 1


def test_every_rule_route_names_its_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    application = create_app()
    assert unmarked_routes(application) == []
    found = _route_roles(application)
    rules = {
        key for key in found if key[1].endswith("/resource-rules") or "/resource-rules/" in key[1]
    }
    assert rules == _READ | _WRITE
    read_roles = found[("GET", "/appointment-types/{type_id}/resource-rules")]
    assert read_roles == set(INVENTORY_READ_ROLES)
    assert all(found[key] == set(INVENTORY_WRITE_ROLES) for key in _WRITE)
    assert "receptionist" not in set().union(*(found[key] for key in rules))
    assert len(list(iter_api_routes(application))) > 0


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


def _item(api: TestClient, cookies: dict[str, str], name: str = "Gloves M") -> str:
    category = api.post("/inventory/categories", cookies=cookies, json={"name": f"Group {name}"})
    assert category.status_code == 201
    item = api.post(
        "/inventory/items",
        cookies=cookies,
        json={"name": name, "category_id": category.json()["id"], "unit": "box"},
    )
    assert item.status_code == 201
    return str(item.json()["id"])


def _type_id(name: str) -> str:
    with Session(get_engine()) as session:
        row = session.scalars(select(AppointmentType).where(AppointmentType.name == name)).one()
        return str(row.id)


def _visit(type_id: str) -> str:
    start = datetime.fromisoformat("2026-10-26T10:00:00+05:30")
    with Session(get_engine()) as session:
        clinician = session.scalars(
            select(AppUser).where(AppUser.email == "clinician@x.test")
        ).one()
        patient = api_patient(session, clinician.clinic_id)
        visit_id = uuid4()
        AppointmentRepository(session, clinician.clinic_id).add(
            Appointment(
                id=visit_id,
                patient_id=patient,
                clinician_user_id=clinician.id,
                appointment_type_id=UUID(type_id),
                starts_at=start,
                ends_at=start + timedelta(minutes=30),
                status="in_progress",
            )
        )
        session.commit()
        return str(visit_id)


def api_patient(session: Session, clinic_id: UUID) -> UUID:
    from dentacircle.services.patient_service import register_patient

    patient = register_patient(
        session,
        clinic_id,
        session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one().id,
        "Sample Ada",
        "9000000001",
        None,
        occurred_at=datetime.fromisoformat("2026-10-26T09:00:00+05:30"),
    )
    return patient.id


def _audits() -> list[AuditEvent]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == "procedure_resource_rule")
                .order_by(AuditEvent.occurred_at, AuditEvent.action)
            )
        )


def _other_clinic() -> None:
    from dentacircle.services.provisioning_service import create_user, get_or_create_clinic

    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Another Synthetic Clinic")
        create_user(
            session,
            clinic.id,
            "other@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["inventory_admin"],
        )
        session.commit()
