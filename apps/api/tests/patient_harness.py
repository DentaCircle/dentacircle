"""A migrated API with one clinic and one user of each role."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.main import create_app
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

PASSWORD = "synthetic-password-marker"
USERS = {
    "clinician@x.test": ["clinician"],
    "receptionist@x.test": ["receptionist"],
    "inventory@x.test": ["inventory_admin"],
    "admin@x.test": ["clinic_admin"],
}


@contextmanager
def patient_api(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    command.upgrade(_config(), "head")
    clear_engine()
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        for email, roles in USERS.items():
            create_user(session, clinic.id, email, "Synthetic Person", PASSWORD, roles)
        session.commit()
    with TestClient(create_app()) as client:
        yield client


def login(client: TestClient, email: str) -> str:
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return str(response.cookies["dc_session"])
