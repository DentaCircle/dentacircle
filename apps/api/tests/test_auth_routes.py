"""Login, the session cookie, logout and the current user."""

from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.core.security import hash_token
from dentacircle.models.auth_session import AuthSession
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_PASSWORD = "synthetic-password-marker"
_EMAIL = "a@x.test"


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("SESSION_TTL_HOURS", "12")
    command.upgrade(_config(), "head")
    from dentacircle.core.database import clear_engine
    from dentacircle.main import create_app

    clear_engine()
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        create_user(session, clinic.id, _EMAIL, "Synthetic Person", _PASSWORD, ["clinician"])
        session.commit()
    return TestClient(create_app())


def test_login_returns_the_user_and_sets_the_cookie(api: TestClient) -> None:
    response = api.post("/auth/login", json={"email": "A@x.test", "password": _PASSWORD})
    assert response.status_code == 200
    user = response.json()["user"]
    assert user["email"] == _EMAIL
    assert user["full_name"] == "Synthetic Person"
    assert user["roles"] == ["clinician"]
    assert user["clinic"]["name"] == "Synthetic Clinic"
    assert "token" not in response.text
    assert _PASSWORD not in response.text

    cookie = response.cookies.get("dc_session")
    assert cookie
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "SameSite=lax" in header
    assert "Path=/" in header
    assert "Max-Age=43200" in header
    assert "Secure" not in header

    with Session(get_engine()) as session:
        stored = session.scalars(select(AuthSession)).one()
        assert stored.token_hash == hash_token(cookie)
        assert cookie not in stored.token_hash


def test_login_rejects_unknown_email_wrong_password_and_inactive_user_alike(
    api: TestClient,
) -> None:
    unknown = api.post("/auth/login", json={"email": "nobody@x.test", "password": _PASSWORD})
    wrong = api.post("/auth/login", json={"email": _EMAIL, "password": "nope"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["code"] == "unauthenticated"
    assert unknown.json() == wrong.json() | {"error": unknown.json()["error"]}
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]
    assert "dc_session" not in unknown.cookies
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(AuthSession)) == 0

    _deactivate(api)
    inactive = api.post("/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    assert inactive.status_code == 401
    assert inactive.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_login_validation_does_not_echo_the_password(api: TestClient) -> None:
    response = api.post("/auth/login", json={"email": _EMAIL})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    response = api.post("/auth/login", json={"email": "not-an-email", "password": _PASSWORD})
    assert _PASSWORD not in response.text


def test_me_returns_the_user_for_a_valid_cookie(api: TestClient) -> None:
    login = api.post("/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    response = api.get("/auth/me", cookies={"dc_session": login.cookies["dc_session"]})
    assert response.status_code == 200
    assert response.json()["email"] == _EMAIL


def test_me_rejects_a_missing_unknown_or_expired_cookie(api: TestClient) -> None:
    missing = api.get("/auth/me")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "unauthenticated"

    unknown = api.get("/auth/me", cookies={"dc_session": "not-a-session"})
    assert unknown.status_code == 401

    login = api.post("/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    _expire_sessions()
    expired = api.get("/auth/me", cookies={"dc_session": login.cookies["dc_session"]})
    assert expired.status_code == 401


def test_me_rejects_a_user_deactivated_after_login(api: TestClient) -> None:
    login = api.post("/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    _deactivate(api)
    response = api.get("/auth/me", cookies={"dc_session": login.cookies["dc_session"]})
    assert response.status_code == 401


def test_logout_deletes_the_session_and_clears_the_cookie(api: TestClient) -> None:
    login = api.post("/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    token = login.cookies["dc_session"]
    response = api.post("/auth/logout", cookies={"dc_session": token})
    assert response.status_code == 204
    assert response.content == b""
    assert "dc_session" in response.headers["set-cookie"]
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(AuthSession)) == 0
    again = api.get("/auth/me", cookies={"dc_session": token})
    assert again.status_code == 401


def test_logout_without_a_cookie_still_returns_204(api: TestClient) -> None:
    response = api.post("/auth/logout")
    assert response.status_code == 204


def _deactivate(api: TestClient) -> None:
    del api
    from dentacircle.models.app_user import AppUser

    with Session(get_engine()) as session:
        user = session.scalars(select(AppUser)).one()
        user.is_active = False
        session.commit()


def _expire_sessions() -> None:
    with Session(get_engine()) as session:
        for auth_session in session.scalars(select(AuthSession)):
            auth_session.expires_at = datetime.now(UTC) - timedelta(hours=1)
        session.commit()
