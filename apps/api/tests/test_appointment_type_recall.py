"""The recall interval on an appointment type."""

from collections.abc import Iterator

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.main import create_app
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_PASSWORD = "synthetic-password-marker"


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    command.upgrade(_config(), "head")
    clear_engine()
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        create_user(
            session, clinic.id, "admin@x.test", "Synthetic Person", _PASSWORD, ["clinic_admin"]
        )
        session.commit()
    with TestClient(create_app()) as client:
        yield client


def test_a_new_clinic_seeds_scaling_at_six_months(api: TestClient) -> None:
    rows = api.get("/appointment-types", cookies=_cookie(api)).json()
    by_name = {row["name"]: row["recall_after_months"] for row in rows}
    assert by_name["Scaling"] == 6
    assert by_name["Consultation"] is None
    assert by_name["Root canal visit"] is None
    assert by_name["Crown visit"] is None
    assert "recall_after_months" in rows[0]


def test_create_accepts_the_interval_and_omitting_it_means_none(api: TestClient) -> None:
    cookie = _cookie(api)
    created = api.post(
        "/appointment-types",
        cookies=cookie,
        json={"name": "Polish", "duration_minutes": 20, "recall_after_months": 12},
    )
    assert created.status_code == 201
    assert created.json()["recall_after_months"] == 12

    omitted = api.post("/appointment-types", cookies=cookie, json={"name": "Review"})
    assert omitted.status_code == 201
    assert omitted.json()["recall_after_months"] is None


def test_put_keeps_the_interval_when_it_is_left_out_and_null_clears_it(api: TestClient) -> None:
    cookie = _cookie(api)
    scaling = _named(api, "Scaling")
    kept = api.put(
        f"/appointment-types/{scaling['id']}",
        cookies=cookie,
        json={"name": "Scaling", "duration_minutes": 30, "is_active": True},
    )
    assert kept.status_code == 200
    assert kept.json()["recall_after_months"] == 6

    cleared = api.put(
        f"/appointment-types/{scaling['id']}",
        cookies=cookie,
        json={
            "name": "Scaling",
            "duration_minutes": 30,
            "is_active": True,
            "recall_after_months": None,
        },
    )
    assert cleared.status_code == 200
    assert cleared.json()["recall_after_months"] is None

    restored = api.put(
        f"/appointment-types/{scaling['id']}",
        cookies=cookie,
        json={
            "name": "Scaling",
            "duration_minutes": 30,
            "is_active": True,
            "recall_after_months": 6,
        },
    )
    assert restored.status_code == 200
    assert restored.json()["recall_after_months"] == 6


@pytest.mark.parametrize("months", [0, 61, 1.5, True, "6"])
def test_a_bad_interval_is_422_on_create_and_update(api: TestClient, months: object) -> None:
    cookie = _cookie(api)
    created = api.post(
        "/appointment-types",
        cookies=cookie,
        json={"name": "Polish", "recall_after_months": months},
    )
    assert created.status_code == 422
    assert created.json()["error"]["code"] == "validation_error"
    assert str(months) not in created.json()["error"]["message"]

    scaling = _named(api, "Scaling")
    updated = api.put(
        f"/appointment-types/{scaling['id']}",
        cookies=cookie,
        json={
            "name": "Scaling",
            "duration_minutes": 30,
            "is_active": True,
            "recall_after_months": months,
        },
    )
    assert updated.status_code == 422
    assert scaling["recall_after_months"] == 6
    listed = _named(api, "Scaling")
    assert listed["recall_after_months"] == 6


def _cookie(api: TestClient) -> dict[str, str]:
    response = api.post("/auth/login", json={"email": "admin@x.test", "password": _PASSWORD})
    assert response.status_code == 200
    token = response.cookies.get("dc_session")
    assert token is not None
    return {"dc_session": token}


def _named(api: TestClient, name: str) -> dict[str, object]:
    rows = api.get("/appointment-types", cookies=_cookie(api)).json()
    return next(row for row in rows if row["name"] == name)
