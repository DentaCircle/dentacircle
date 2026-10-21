"""Database helpers shared by the test harness, and visit helpers shared by loop tests."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine, to_psycopg_url, to_sqlalchemy_url

CLINIC_ZONE = ZoneInfo("Asia/Kolkata")


def create_throwaway_database(database_url: str) -> str:
    name = f"dentacircle_test_{uuid4().hex}"
    admin_url = to_psycopg_url(_with_database(database_url, "postgres"))
    with psycopg.connect(admin_url, autocommit=True, connect_timeout=5) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return _with_database(database_url, name)


def drop_database(database_url: str) -> None:
    name = urlsplit(database_url).path.lstrip("/")
    admin_url = to_psycopg_url(_with_database(database_url, "postgres"))
    with psycopg.connect(admin_url, autocommit=True, connect_timeout=5) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (name,),
        )
        connection.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


@contextmanager
def rollback_session(database_url: str) -> Iterator[Session]:
    """A session whose commit is undone when the context exits."""
    engine = create_engine(to_sqlalchemy_url(database_url), connect_args={"connect_timeout": 5})
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


def next_open_slot(
    api: TestClient,
    cookies: dict[str, str],
    clinician_id: str,
    type_id: str,
    slot_index: int,
) -> str:
    """The first open slot at this index, skipping closed Sundays."""
    today = datetime.now(UTC).astimezone(CLINIC_ZONE).date()
    for offset in range(8):
        day = today + timedelta(days=offset)
        if day.weekday() == 6:
            continue
        found = api.get(
            "/appointments/availability",
            cookies=cookies,
            params={
                "date": day.isoformat(),
                "clinician_id": clinician_id,
                "appointment_type_id": type_id,
            },
        )
        assert found.status_code == 200
        slots = found.json()["slots"]
        if len(slots) > slot_index:
            return str(slots[slot_index]["starts_at"])
    raise AssertionError("no open slot")


def place_visit_today(visit_id: str, hour: int) -> None:
    """Arrived is only allowed on the visit's clinic-local day. A later slot is moved."""
    today = datetime.now(UTC).astimezone(CLINIC_ZONE).date()
    start = datetime(today.year, today.month, today.day, hour, 0, tzinfo=CLINIC_ZONE)
    end = start + timedelta(minutes=30)
    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE appointment SET starts_at = :start, ends_at = :end WHERE id = :id"),
            {"start": start, "end": end, "id": UUID(visit_id)},
        )
        session.commit()


def post_visit_status(
    api: TestClient,
    cookies: dict[str, str],
    visit_id: str,
    status: str,
    follow_up_due_on: str | None = None,
) -> None:
    body: dict[str, str] = {"status": status}
    if follow_up_due_on is not None:
        body["follow_up_due_on"] = follow_up_due_on
    response = api.post(f"/appointments/{visit_id}/status", cookies=cookies, json=body)
    assert response.status_code == 200
    assert response.json()["status"] == status


def _with_database(database_url: str, name: str) -> str:
    parts = urlsplit(database_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))
