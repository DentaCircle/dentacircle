"""Document routes: roles, order of checks, limits, types, tenancy, headers and no echo."""

import logging
from collections.abc import Iterator
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.document import (
    DOCUMENT_READ_ROLES,
    DOCUMENT_WRITE_ROLES,
    MAX_DOCUMENT_BYTES,
)
from dentacircle.integrations.storage import get_storage
from dentacircle.integrations.storage.memory import MemoryStorage
from dentacircle.main import create_app
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.document import Document
from dentacircle.models.patient import Patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import PASSWORD, login, patient_api
from tests.test_access import iter_api_routes, unmarked_routes
from tests.test_timeline_routes import _route_roles

_PDF = b"%PDF-1.7\nsynthetic body"
_PNG = b"\x89PNG\r\n\x1a\nsynthetic body"
_JPEG = b"\xff\xd8\xff\xe0synthetic body"
_NAME = "distinctive-filename-marker.pdf"
_BODY_MARKER = b"distinctive-content-marker"
_ROLES = ("receptionist", "clinician", "clinic_admin", "inventory_admin")
_EMAILS = {
    "receptionist": "receptionist@x.test",
    "clinician": "clinician@x.test",
    "clinic_admin": "admin@x.test",
    "inventory_admin": "inventory@x.test",
}


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


@pytest.fixture
def api(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch, storage: MemoryStorage
) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        cast(FastAPI, client.app).dependency_overrides[get_storage] = lambda: storage
        yield client


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


def _patient(api: TestClient, cookies: dict[str, str] | None = None) -> str:
    response = api.post(
        "/patients",
        cookies=cookies if cookies is not None else _cookie(api),
        json={"full_name": "Sample Ada", "phone": "9000000001"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _post(
    api: TestClient,
    patient_id: str,
    *,
    cookies: dict[str, str] | None = None,
    name: str | None = _NAME,
    data: bytes | Iterator[bytes] = _PDF,
    content_type: str | None = "application/pdf",
) -> Response:
    headers = {} if content_type is None else {"Content-Type": content_type}
    params = {} if name is None else {"filename": name}
    response: Response = api.post(
        f"/patients/{patient_id}/documents",
        cookies=cookies if cookies is not None else _cookie(api),
        params=params,
        content=data,
        headers=headers,
    )
    return response


def _server_log(caplog: pytest.LogCaptureFixture) -> str:
    """The API's own log lines. The test client logs the request URL, which is not the server."""
    return "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith("dentacircle")
    )


def _upload_ok(api: TestClient, patient_id: str, name: str = "report.pdf") -> dict[str, object]:
    response = _post(api, patient_id, name=name)
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def _count(model: type[Document] | type[AuditEvent]) -> int:
    with Session(get_engine()) as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _audit_actions() -> list[str]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(select(AuditEvent.action).where(AuditEvent.entity_type == "document"))
        )


def _set_inactive(patient_id: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(Patient, UUID(patient_id))
        assert row is not None
        row.status = "inactive"
        session.commit()


def _other_clinic_cookies(api: TestClient) -> dict[str, str]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Another Synthetic Clinic")
        create_user(session, clinic.id, "other@x.test", "Other Person", PASSWORD, ["receptionist"])
        session.commit()
    return _cookie(api, "other@x.test")


# --- upload ------------------------------------------------------------------


def test_an_upload_returns_201_and_the_item(api: TestClient, storage: MemoryStorage) -> None:
    patient_id = _patient(api)
    response = _post(api, patient_id, name=" a/b\\report.pdf ")
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "filename",
        "content_type",
        "size_bytes",
        "uploaded_at",
        "uploaded_by",
    }
    assert body["filename"] == "report.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["size_bytes"] == len(_PDF)
    assert set(body["uploaded_by"]) == {"id", "name"}
    assert body["uploaded_at"].endswith("+05:30")
    assert list(storage.files) == [f"{_clinic_id()}/{body['id']}"]


def _clinic_id() -> UUID:
    from dentacircle.models.clinic import Clinic

    with Session(get_engine()) as session:
        return session.scalars(select(Clinic.id)).one()


@pytest.mark.parametrize("role", _ROLES)
def test_roles_for_upload(api: TestClient, role: str) -> None:
    patient_id = _patient(api)
    response = _post(api, patient_id, cookies=_cookie(api, _EMAILS[role]))
    if role in DOCUMENT_WRITE_ROLES:
        assert response.status_code == 201
        assert _audit_actions() == ["create"]
    else:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"
        assert _count(Document) == 0
        assert _audit_actions() == []


def test_no_session_is_401(api: TestClient) -> None:
    patient_id = _patient(api)
    api.cookies.clear()
    response = api.post(
        f"/patients/{patient_id}/documents",
        params={"filename": "x.pdf"},
        content=_PDF,
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 401
    assert _count(Document) == 0


def test_checks_run_session_role_input_patient_then_the_rest(
    api: TestClient, storage: MemoryStorage
) -> None:
    missing = str(uuid4())
    oversize = b"%PDF-" + b"x" * MAX_DOCUMENT_BYTES
    api.cookies.clear()
    # 401 first, whatever else is wrong.
    anonymous = api.post(
        f"/patients/{missing}/documents", params={"filename": "/"}, content=oversize
    )
    assert anonymous.status_code == 401
    # 403 next.
    denied = _post(api, missing, cookies=_cookie(api, "inventory@x.test"), name="/", data=oversize)
    assert denied.status_code == 403
    cookies = _cookie(api)
    # 422 on the input beats 404 on the patient, and the body is not read for it.
    for name in (None, "", "   ", "folder/", "\x00"):
        invalid = _post(api, missing, cookies=cookies, name=name, data=oversize)
        assert invalid.status_code == 422, name
        assert invalid.json()["error"]["code"] == "validation_error"
    too_long = _post(api, missing, cookies=cookies, name="x" * 201)
    assert too_long.status_code == 422
    bad_id = _post(api, "not-a-uuid", cookies=cookies)
    assert bad_id.status_code == 422
    # 404 beats the body checks: 413, 415, empty body.
    for data, content_type in (
        (oversize, "application/pdf"),
        (b"GIF89a", "image/gif"),
        (b"", None),
    ):
        unknown = _post(api, missing, cookies=cookies, data=data, content_type=content_type)
        assert unknown.status_code == 404
    # Then the rest, in order: 413, then 422 for an empty body, then 415, then 409.
    patient_id = _patient(api)
    _set_inactive(patient_id)
    assert _post(api, patient_id, data=oversize).status_code == 413
    assert _post(api, patient_id, data=b"", content_type=None).status_code == 422
    assert _post(api, patient_id, data=b"GIF89a", content_type="image/gif").status_code == 415
    assert _post(api, patient_id).status_code == 409
    assert storage.files == {}


def test_a_file_of_exactly_the_limit_is_stored(api: TestClient, storage: MemoryStorage) -> None:
    patient_id = _patient(api)
    data = _PDF + b"x" * (MAX_DOCUMENT_BYTES - len(_PDF))
    response = _post(api, patient_id, data=data)
    assert response.status_code == 201
    assert response.json()["size_bytes"] == MAX_DOCUMENT_BYTES
    assert len(storage.files) == 1


def test_a_file_over_the_limit_is_413_and_nothing_is_stored(
    api: TestClient, storage: MemoryStorage
) -> None:
    patient_id = _patient(api)
    data = _PDF + b"x" * (MAX_DOCUMENT_BYTES - len(_PDF) + 1)
    response = _post(api, patient_id, data=data)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    assert storage.files == {}
    assert _count(Document) == 0
    assert _audit_actions() == []


def test_the_limit_is_counted_from_the_stream_not_from_content_length(
    api: TestClient, storage: MemoryStorage
) -> None:
    patient_id = _patient(api)
    chunk = b"x" * (1024 * 1024)

    def stream() -> Iterator[bytes]:
        yield _PDF
        for _ in range(9):
            yield chunk

    request = api.build_request(
        "POST",
        f"/patients/{patient_id}/documents",
        params={"filename": "big.pdf"},
        content=stream(),
        headers={"Content-Type": "application/pdf"},
        cookies=_cookie(api),
    )
    assert "content-length" not in request.headers
    assert request.headers["transfer-encoding"] == "chunked"
    response = api.send(request)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    assert storage.files == {}


def test_a_small_chunked_body_is_stored(api: TestClient, storage: MemoryStorage) -> None:
    patient_id = _patient(api)
    response = _post(api, patient_id, data=iter([_PDF[:5], _PDF[5:]]))
    assert response.status_code == 201
    assert next(iter(storage.files.values())) == _PDF


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (b"GIF89a....", "image/gif"),
        (b"GIF89a....", "image/png"),
        (_PDF, "image/png"),
        (_PNG, "application/pdf"),
        (_PDF, None),
        (_PDF, "application/octet-stream"),
        (b"<script>alert(1)</script>", "application/pdf"),
        (b"MZ\x90\x00", "application/pdf"),
    ],
)
def test_a_wrong_or_disagreeing_type_is_415(
    api: TestClient, storage: MemoryStorage, data: bytes, content_type: str | None
) -> None:
    patient_id = _patient(api)
    response = _post(api, patient_id, data=data, content_type=content_type)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"
    assert storage.files == {}
    assert _count(Document) == 0
    assert _audit_actions() == []


@pytest.mark.parametrize(
    ("data", "content_type"),
    [(_PDF, "application/pdf"), (_PNG, "image/png"), (_JPEG, "image/jpeg")],
)
def test_the_three_types_are_accepted(api: TestClient, data: bytes, content_type: str) -> None:
    patient_id = _patient(api)
    response = _post(api, patient_id, data=data, content_type=content_type)
    assert response.status_code == 201
    assert response.json()["content_type"] == content_type


def test_an_empty_body_is_422(api: TestClient, storage: MemoryStorage) -> None:
    patient_id = _patient(api)
    response = _post(api, patient_id, data=b"", content_type="application/pdf")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert storage.files == {}


def test_an_inactive_patient_is_409_and_can_still_be_read(
    api: TestClient, storage: MemoryStorage
) -> None:
    patient_id = _patient(api)
    document = _upload_ok(api, patient_id)
    _set_inactive(patient_id)
    refused = _post(api, patient_id)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "patient_inactive"
    assert refused.json()["error"]["message"] == "This patient is inactive."
    assert len(storage.files) == 1
    assert _count(Document) == 1
    cookies = _cookie(api)
    assert api.get(f"/patients/{patient_id}/documents", cookies=cookies).status_code == 200
    file = api.get(f"/patients/{patient_id}/documents/{document['id']}/file", cookies=cookies)
    assert file.status_code == 200


def test_another_clinics_patient_is_404(api: TestClient, storage: MemoryStorage) -> None:
    patient_id = _patient(api)
    other = _other_clinic_cookies(api)
    assert _post(api, patient_id, cookies=other).status_code == 404
    assert storage.files == {}
    assert _count(Document) == 0


def test_failed_uploads_write_no_audit_row_and_a_success_writes_one(api: TestClient) -> None:
    patient_id = _patient(api)
    before = _count(AuditEvent)
    _post(api, patient_id, data=b"GIF89a", content_type="image/gif")
    _post(api, patient_id, data=b"", content_type=None)
    _post(api, patient_id, name="/")
    assert _count(AuditEvent) == before
    _upload_ok(api, patient_id)
    assert _count(AuditEvent) == before + 1
    assert _audit_actions() == ["create"]


def test_no_error_or_log_line_echoes_the_filename_or_content(
    api: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    patient_id = _patient(api)
    inactive_id = _patient(api)
    _set_inactive(inactive_id)
    marker_name = "distinctive-filename-marker.pdf"
    cases = [
        _post(api, patient_id, name=marker_name, data=b"GIF89a" + _BODY_MARKER, content_type="x/y"),
        _post(
            api,
            patient_id,
            name=marker_name,
            data=_PDF + _BODY_MARKER + b"x" * MAX_DOCUMENT_BYTES,
        ),
        _post(api, patient_id, name=marker_name, data=b"", content_type=None),
        _post(api, inactive_id, name=marker_name, data=_PDF + _BODY_MARKER),
        _post(api, patient_id, name=marker_name + "x" * 300, data=_PDF + _BODY_MARKER),
        _post(api, str(uuid4()), name=marker_name, data=_PDF + _BODY_MARKER),
    ]
    assert [case.status_code for case in cases] == [415, 413, 422, 409, 422, 404]
    for case in cases:
        assert "distinctive" not in case.text
        assert "marker" not in case.text
    assert "distinctive" not in _server_log(caplog)


def test_the_logs_stay_clean_when_everything_is_logged(
    api: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    patient_id = _patient(api)
    with caplog.at_level(logging.DEBUG):
        _post(api, patient_id, name="distinctive-name.pdf", data=_PDF + _BODY_MARKER)
        _post(api, patient_id, name="distinctive-name.pdf", data=b"GIF89a" + _BODY_MARKER)
    assert "distinctive" not in _server_log(caplog)
    assert "request_id" in _server_log(caplog)


# --- list ----------------------------------------------------------------------


def test_the_list_shape_order_and_paging(api: TestClient) -> None:
    patient_id = _patient(api)
    first = _upload_ok(api, patient_id, "first.pdf")
    second = _upload_ok(api, patient_id, "second.pdf")
    cookies = _cookie(api, "clinician@x.test")
    found = api.get(f"/patients/{patient_id}/documents", cookies=cookies)
    assert found.status_code == 200
    body = found.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert (body["total"], body["page"], body["page_size"]) == (2, 1, 20)
    assert [item["id"] for item in body["items"]] == [second["id"], first["id"]]
    assert set(body["items"][0]) == {
        "id",
        "filename",
        "content_type",
        "size_bytes",
        "uploaded_at",
        "uploaded_by",
    }
    paged = api.get(
        f"/patients/{patient_id}/documents", cookies=cookies, params={"page": 2, "page_size": 1}
    )
    assert [item["id"] for item in paged.json()["items"]] == [first["id"]]
    assert paged.json()["total"] == 2


def test_list_checks_run_session_then_role_then_validation_then_patient(api: TestClient) -> None:
    missing = str(uuid4())
    api.cookies.clear()
    assert api.get(f"/patients/{missing}/documents", params={"page": 0}).status_code == 401
    denied = api.get(
        f"/patients/{missing}/documents",
        cookies=_cookie(api, "inventory@x.test"),
        params={"page": 0},
    )
    assert denied.status_code == 403
    cookies = _cookie(api, "clinician@x.test")
    for params in ({"page": 0}, {"page_size": 0}, {"page_size": 101}):
        response = api.get(f"/patients/{missing}/documents", cookies=cookies, params=params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
    assert api.get(f"/patients/{missing}/documents", cookies=cookies).status_code == 404
    assert api.get("/patients/not-a-uuid/documents", cookies=cookies).status_code == 422


@pytest.mark.parametrize("role", _ROLES)
def test_roles_for_list_and_download(api: TestClient, role: str) -> None:
    patient_id = _patient(api)
    document = _upload_ok(api, patient_id)
    cookies = _cookie(api, _EMAILS[role])
    listed = api.get(f"/patients/{patient_id}/documents", cookies=cookies)
    file = api.get(f"/patients/{patient_id}/documents/{document['id']}/file", cookies=cookies)
    if role in DOCUMENT_READ_ROLES:
        assert listed.status_code == 200
        assert file.status_code == 200
    else:
        assert listed.status_code == 403
        assert file.status_code == 403
        assert "report.pdf" not in listed.text
    api.cookies.clear()
    assert api.get(f"/patients/{patient_id}/documents").status_code == 401
    assert api.get(f"/patients/{patient_id}/documents/{document['id']}/file").status_code == 401


def test_another_clinic_cannot_list_or_download(api: TestClient) -> None:
    patient_id = _patient(api)
    document = _upload_ok(api, patient_id)
    other = _other_clinic_cookies(api)
    assert api.get(f"/patients/{patient_id}/documents", cookies=other).status_code == 404
    stolen = api.get(f"/patients/{patient_id}/documents/{document['id']}/file", cookies=other)
    assert stolen.status_code == 404
    assert "synthetic" not in stolen.text


# --- download --------------------------------------------------------------------


def test_a_download_streams_the_bytes_with_safe_headers(api: TestClient) -> None:
    patient_id = _patient(api)
    document = _upload_ok(api, patient_id, 'my "report" \u00e9.pdf')
    response = api.get(
        f"/patients/{patient_id}/documents/{document['id']}/file", cookies=_cookie(api)
    )
    assert response.status_code == 200
    assert response.content == _PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["content-length"] == str(len(_PDF))
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "inline" not in disposition
    assert 'filename="my _report_ _.pdf"' in disposition
    assert "filename*=UTF-8''my%20%22report%22%20%C3%A9.pdf" in disposition


def test_a_png_download_has_the_stored_type(api: TestClient) -> None:
    patient_id = _patient(api)
    response = _post(api, patient_id, data=_PNG, content_type="image/png")
    document_id = response.json()["id"]
    found = api.get(f"/patients/{patient_id}/documents/{document_id}/file", cookies=_cookie(api))
    assert found.headers["content-type"] == "image/png"
    assert found.content == _PNG


def test_a_document_of_another_patient_or_an_unknown_id_is_404(api: TestClient) -> None:
    patient_id = _patient(api)
    other_patient = _patient(api)
    document = _upload_ok(api, patient_id)
    cookies = _cookie(api)
    wrong_patient = api.get(
        f"/patients/{other_patient}/documents/{document['id']}/file", cookies=cookies
    )
    assert wrong_patient.status_code == 404
    unknown = api.get(f"/patients/{patient_id}/documents/{uuid4()}/file", cookies=cookies)
    assert unknown.status_code == 404
    bad = api.get(f"/patients/{patient_id}/documents/not-a-uuid/file", cookies=cookies)
    assert bad.status_code == 422


def test_a_missing_file_is_404_not_an_error_page(api: TestClient, storage: MemoryStorage) -> None:
    patient_id = _patient(api)
    document = _upload_ok(api, patient_id)
    storage.files.clear()
    response = api.get(
        f"/patients/{patient_id}/documents/{document['id']}/file", cookies=_cookie(api)
    )
    assert response.status_code == 404


def test_the_storage_key_comes_from_the_row(api: TestClient, storage: MemoryStorage) -> None:
    patient_id = _patient(api)
    first = _upload_ok(api, patient_id, "first.pdf")
    second = _post(api, patient_id, data=_PDF + b"second").json()
    first_key = f"{_clinic_id()}/{first['id']}"
    second_key = f"{_clinic_id()}/{second['id']}"
    cookies = _cookie(api)
    got = api.get(f"/patients/{patient_id}/documents/{second['id']}/file", cookies=cookies)
    assert got.content == storage.files[second_key]
    assert storage.files[first_key] != storage.files[second_key]


def test_list_and_download_write_no_audit_row(api: TestClient) -> None:
    patient_id = _patient(api)
    document = _upload_ok(api, patient_id)
    before = _count(AuditEvent)
    cookies = _cookie(api)
    api.get(f"/patients/{patient_id}/documents", cookies=cookies)
    api.get(f"/patients/{patient_id}/documents/{document['id']}/file", cookies=cookies)
    assert _count(AuditEvent) == before


# --- the route table ---------------------------------------------------------------


def test_every_document_route_names_its_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    application = create_app()
    assert unmarked_routes(application) == []
    found = _route_roles(application)
    assert found[("POST", "/patients/{patient_id}/documents")] == set(DOCUMENT_WRITE_ROLES)
    assert found[("GET", "/patients/{patient_id}/documents")] == set(DOCUMENT_READ_ROLES)
    assert found[("GET", "/patients/{patient_id}/documents/{document_id}/file")] == set(
        DOCUMENT_READ_ROLES
    )
    document_routes = [key for key in found if "documents" in key[1]]
    assert sorted(document_routes) == [
        ("GET", "/patients/{patient_id}/documents"),
        ("GET", "/patients/{patient_id}/documents/{document_id}/file"),
        ("POST", "/patients/{patient_id}/documents"),
    ]
    assert "inventory_admin" not in set().union(*(found[key] for key in document_routes))
    assert len(list(iter_api_routes(application))) > 0
