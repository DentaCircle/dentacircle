"""Lab work routes: roles, order of checks, tenancy, filters, paging and no echo."""

import logging
from collections.abc import Iterator
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.lab_work import LAB_WORK_ROLES
from dentacircle.main import create_app
from dentacircle.services.appointment_service import book_appointment
from dentacircle.services.patient_service import set_patient_status
from tests.patient_harness import login, patient_api
from tests.test_access import iter_api_routes, unmarked_routes
from tests.test_timeline_routes import _route_roles

_ZONE = ZoneInfo("Asia/Kolkata")
_MARKER = "distinctive-crown-marker"
_ROLES = ("receptionist", "clinician", "clinic_admin", "inventory_admin")
_EMAILS = {
    "receptionist": "receptionist@x.test",
    "clinician": "clinician@x.test",
    "clinic_admin": "admin@x.test",
    "inventory_admin": "inventory@x.test",
}


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_create_returns_the_item_and_a_pending_row(api: TestClient) -> None:
    patient_id = _patient(api)
    response = api.post(
        f"/patients/{patient_id}/lab-work",
        cookies=_cookie(api),
        json={"title": f"  {_MARKER}  ", "expected_on": _day(1)},
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "status",
        "title",
        "expected_on",
        "overdue",
        "appointment",
        "patient",
        "created_at",
        "created_by",
    }
    assert body["status"] == "pending"
    assert body["title"] == _MARKER
    assert body["expected_on"] == _day(1)
    assert body["overdue"] is False
    assert body["appointment"] is None
    assert body["patient"]["id"] == patient_id
    assert body["created_at"].endswith("+05:30")
    listed = api.get(f"/patients/{patient_id}/timeline", cookies=_cookie(api))
    created = [item for item in listed.json()["items"] if item["kind"] == "lab_work_created"]
    assert created[0]["subject"] == {"lab_work_id": body["id"], "title": _MARKER}


def test_a_related_visit_is_read_live(api: TestClient) -> None:
    patient_id = _patient(api)
    visit_id = _book(api, patient_id)
    response = api.post(
        f"/patients/{patient_id}/lab-work",
        cookies=_cookie(api),
        json={"title": "Crown", "appointment_id": visit_id},
    )
    assert response.status_code == 201
    appointment = response.json()["appointment"]
    assert appointment["id"] == visit_id
    assert appointment["type_name"] == "Consultation"
    assert appointment["starts_at"].endswith("+05:30")


def test_checks_run_in_order(api: TestClient) -> None:
    missing = str(uuid4())
    bad = {"title": " ", "expected_on": "yesterday", "note": "secret"}
    anonymous = api.post(f"/patients/{missing}/lab-work", json=bad)
    assert anonymous.status_code == 401
    denied = api.post(
        f"/patients/{missing}/lab-work",
        cookies=_cookie(api, "inventory@x.test"),
        json=bad,
    )
    assert denied.status_code == 403
    cookies = _cookie(api)
    invalid = api.post(f"/patients/{missing}/lab-work", cookies=cookies, json={"title": " "})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    early = api.post(
        f"/patients/{missing}/lab-work",
        cookies=cookies,
        json={"title": "Crown", "expected_on": _day(-1)},
    )
    assert early.status_code == 422
    absent = api.post(f"/patients/{missing}/lab-work", cookies=cookies, json={"title": "Crown"})
    assert absent.status_code == 404
    patient_id = _patient(api)
    _deactivate(patient_id)
    inactive = api.post(
        f"/patients/{patient_id}/lab-work", cookies=cookies, json={"title": "Crown"}
    )
    assert inactive.status_code == 409
    assert inactive.json()["error"]["code"] == "patient_inactive"


def test_status_checks_run_in_order(api: TestClient) -> None:
    missing = str(uuid4())
    anonymous = api.post(f"/lab-work/{missing}/status", json={"status": "sent"})
    assert anonymous.status_code == 401
    denied = api.post(
        f"/lab-work/{missing}/status",
        cookies=_cookie(api, "inventory@x.test"),
        json={"status": "ready"},
    )
    assert denied.status_code == 403
    cookies = _cookie(api)
    unknown = api.post(f"/lab-work/{missing}/status", cookies=cookies, json={"status": "sent"})
    assert unknown.status_code == 422
    absent = api.post(f"/lab-work/{missing}/status", cookies=cookies, json={"status": "pending"})
    assert absent.status_code == 404
    patient_id = _patient(api)
    lab_id = _create(api, patient_id)
    pending = api.post(f"/lab-work/{lab_id}/status", cookies=cookies, json={"status": "pending"})
    assert pending.status_code == 409
    assert pending.json()["error"]["code"] == "invalid_status"
    skipped = api.post(f"/lab-work/{lab_id}/status", cookies=cookies, json={"status": "collected"})
    assert skipped.status_code == 409


def test_ready_then_collected_and_the_follow_up_stays_open(api: TestClient) -> None:
    patient_id = _patient(api)
    lab_id = _create(api, patient_id)
    cookies = _cookie(api)
    ready = api.post(f"/lab-work/{lab_id}/status", cookies=cookies, json={"status": "ready"})
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    follow_up = api.get(f"/patients/{patient_id}/follow-up", cookies=cookies)
    assert follow_up.status_code == 200
    assert follow_up.json()["follow_up"]["due_on"] == _today()
    assert follow_up.json()["follow_up"]["status"] == "scheduled"
    again = api.post(f"/lab-work/{lab_id}/status", cookies=cookies, json={"status": "ready"})
    assert again.status_code == 409
    collected = api.post(
        f"/lab-work/{lab_id}/status", cookies=cookies, json={"status": "collected"}
    )
    assert collected.status_code == 200
    still = api.get(f"/patients/{patient_id}/follow-up", cookies=cookies)
    assert still.json()["follow_up"]["status"] == "scheduled"
    final = api.post(f"/lab-work/{lab_id}/status", cookies=cookies, json={"status": "cancelled"})
    assert final.status_code == 409


@pytest.mark.parametrize("role", _ROLES)
def test_each_role_on_create_and_on_the_lists(api: TestClient, role: str) -> None:
    patient_id = _patient(api)
    cookies = _cookie(api, _EMAILS[role])
    created = api.post(f"/patients/{patient_id}/lab-work", cookies=cookies, json={"title": "Crown"})
    listed = api.get(f"/patients/{patient_id}/lab-work", cookies=cookies)
    clinic = api.get("/lab-work", cookies=cookies)
    if role in LAB_WORK_ROLES:
        assert created.status_code == 201
        assert listed.status_code == 200
        assert clinic.status_code == 200
    else:
        assert created.status_code == 403
        assert listed.status_code == 403
        assert clinic.status_code == 403


def test_the_patient_list_is_newest_first_and_paging_matches_documents(api: TestClient) -> None:
    patient_id = _patient(api)
    cookies = _cookie(api)
    first = _create(api, patient_id, "Crown")
    second = _create(api, patient_id, "Bridge")
    found = api.get(f"/patients/{patient_id}/lab-work", cookies=cookies)
    assert found.status_code == 200
    body = found.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert [item["id"] for item in body["items"]] == [second, first]
    paged = api.get(
        f"/patients/{patient_id}/lab-work", cookies=cookies, params={"page": 2, "page_size": 1}
    )
    assert [item["id"] for item in paged.json()["items"]] == [first]
    assert (
        api.get(f"/patients/{patient_id}/lab-work", cookies=cookies, params={"page": 0}).status_code
        == 422
    )
    assert api.get(f"/patients/{uuid4()}/lab-work", cookies=cookies).status_code == 404


def test_the_clinic_list_filters_open_work_and_calculates_overdue(api: TestClient) -> None:
    patient_id = _patient(api)
    cookies = _cookie(api)
    pending = _create(api, patient_id, "Crown", expected_on=_day(1))
    ready = _create(api, patient_id, "Bridge", expected_on=_day(3))
    collected = _create(api, patient_id, "Denture")
    api.post(f"/lab-work/{ready}/status", cookies=cookies, json={"status": "ready"})
    api.post(f"/lab-work/{collected}/status", cookies=cookies, json={"status": "cancelled"})
    _age(pending)
    open_page = api.get("/lab-work", cookies=cookies)
    assert open_page.status_code == 200
    open_titles = [item["title"] for item in open_page.json()["items"]]
    assert open_titles == ["Crown", "Bridge"]
    flags = {item["title"]: item["overdue"] for item in open_page.json()["items"]}
    assert flags == {"Crown": True, "Bridge": False}
    everything = api.get("/lab-work", cookies=cookies, params={"view": "all"})
    assert [item["title"] for item in everything.json()["items"]] == [
        "Crown",
        "Bridge",
        "Denture",
    ]
    one = api.get(f"/lab-work/{pending}", cookies=cookies)
    assert one.status_code == 200
    assert one.json()["patient"]["full_name"] == "Sample Ada"
    assert one.json()["overdue"] is True
    assert api.get("/lab-work", cookies=cookies, params={"view": "sent"}).status_code == 422
    assert api.get(f"/lab-work/{uuid4()}", cookies=cookies).status_code == 404


def test_errors_do_not_echo_the_title_or_a_submitted_id(
    api: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    patient_id = _patient(api)
    lab_id = _create(api, patient_id, _MARKER)
    marker = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    cookies = _cookie(api)
    with caplog.at_level(logging.DEBUG):
        missing = api.get(f"/lab-work/{marker}", cookies=cookies)
        _deactivate(patient_id)
        refused = api.post(
            f"/patients/{patient_id}/lab-work",
            cookies=cookies,
            json={"title": _MARKER},
        )
        invalid = api.post(
            f"/patients/{uuid4()}/lab-work",
            cookies=cookies,
            json={"title": "x" * 201},
        )
        wrong_visit = api.post(
            f"/patients/{patient_id}/lab-work",
            cookies=cookies,
            json={"title": _MARKER, "appointment_id": marker},
        )
    assert missing.status_code == 404
    assert refused.status_code == 409
    assert invalid.status_code == 422
    assert wrong_visit.status_code == 404
    for response in (missing, refused, invalid, wrong_visit):
        assert _MARKER not in response.text
        assert marker not in response.text
        assert lab_id not in response.text
    log = "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith("dentacircle")
    )
    assert _MARKER not in log
    posted = "\n".join(line for line in log.splitlines() if "method=POST" in line)
    assert marker not in posted


def test_another_clinic_cannot_see_the_item(api: TestClient) -> None:
    patient_id = _patient(api)
    lab_id = _create(api, patient_id, _MARKER)
    _other_clinic(api)
    stolen = api.get(f"/lab-work/{lab_id}", cookies=_cookie(api, "other@x.test"))
    assert stolen.status_code == 404
    assert _MARKER not in stolen.text


def test_every_lab_route_names_its_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    application = create_app()
    assert unmarked_routes(application) == []
    found = _route_roles(application)
    lab_routes = [key for key in found if "lab-work" in key[1]]
    assert sorted(lab_routes) == [
        ("GET", "/lab-work"),
        ("GET", "/lab-work/{lab_work_id}"),
        ("GET", "/patients/{patient_id}/lab-work"),
        ("POST", "/lab-work/{lab_work_id}/status"),
        ("POST", "/patients/{patient_id}/lab-work"),
    ]
    assert all(found[key] == set(LAB_WORK_ROLES) for key in lab_routes)
    assert len(list(iter_api_routes(application))) > 0


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


def _patient(api: TestClient) -> str:
    response = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": "Sample Ada", "phone": "9000000001"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _create(
    api: TestClient, patient_id: str, title: str = "Crown", expected_on: str | None = None
) -> str:
    body: dict[str, str] = {"title": title}
    if expected_on is not None:
        body["expected_on"] = expected_on
    response = api.post(f"/patients/{patient_id}/lab-work", cookies=_cookie(api), json=body)
    assert response.status_code == 201
    return str(response.json()["id"])


def _book(api: TestClient, patient_id: str) -> str:
    from uuid import UUID

    from sqlalchemy import select

    from dentacircle.models.app_user import AppUser
    from dentacircle.models.appointment_type import AppointmentType

    start = datetime.now(_ZONE) + timedelta(days=1)
    start = start.replace(hour=10, minute=0, second=0, microsecond=0)
    while start.weekday() == 6:
        start += timedelta(days=1)
    with Session(get_engine()) as session:
        clinician = session.scalars(
            select(AppUser).where(AppUser.email == "clinician@x.test")
        ).one()
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinician.clinic_id)
            )
            if row.name == "Consultation"
        )
        visit = book_appointment(
            session,
            clinician.clinic_id,
            clinician.id,
            UUID(patient_id),
            clinician.id,
            consultation.id,
            start,
            datetime.now(_ZONE),
        )
        session.commit()
        return str(visit.id)


def _deactivate(patient_id: str) -> None:
    from sqlalchemy import select

    from dentacircle.models.app_user import AppUser
    from dentacircle.models.patient import Patient

    with Session(get_engine()) as session:
        patient = session.scalars(select(Patient).where(Patient.id == patient_id)).one()
        actor = session.scalars(select(AppUser).where(AppUser.email == "receptionist@x.test")).one()
        set_patient_status(session, patient.clinic_id, actor.id, patient.id, "inactive")
        session.commit()


def _age(lab_id: str) -> None:
    with Session(get_engine()) as session:
        session.execute(
            text(
                "UPDATE lab_work SET expected_on = CURRENT_DATE - interval '1 day' WHERE id = :id"
            ),
            {"id": lab_id},
        )
        session.commit()


def _other_clinic(api: TestClient) -> str:
    from dentacircle.services.provisioning_service import create_user, get_or_create_clinic

    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Another Synthetic Clinic")
        create_user(
            session,
            clinic.id,
            "other@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        session.commit()
        return str(clinic.id)


def _today() -> str:
    return datetime.now(_ZONE).date().isoformat()


def _day(offset: int) -> str:
    return (datetime.now(_ZONE).date() + timedelta(days=offset)).isoformat()
