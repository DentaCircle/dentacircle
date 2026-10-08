"""Paging and search. The rules live in domain.parse_search; these tests check the list."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.patient import parse_search
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api


def test_a_blank_query_is_unfiltered() -> None:
    assert parse_search(None).mode == "all"
    assert parse_search("   ").mode == "all"


def test_patient_id_forms_match_the_number() -> None:
    for raw in ("P-0012", "p0012", "p-12", "12", "0012"):
        parsed = parse_search(raw)
        assert parsed.mode == "number"
        assert parsed.patient_number == 12
    assert parse_search("P-10000").patient_number == 10000


def test_a_short_number_is_not_a_phone_fragment() -> None:
    """`12` is patient 12. A 5-digit string is a phone fragment, including `98765`."""
    assert parse_search("9876").mode == "number"
    parsed = parse_search("98765")
    assert parsed.mode == "phone"
    assert parsed.phone_digits == "98765"
    assert parse_search("10000").mode == "phone"


@pytest.mark.parametrize(
    ("raw", "digits"),
    [
        ("98765", "98765"),
        ("+91 98765 43210", "919876543210"),
        ("(98765) 43210", "9876543210"),
    ],
)
def test_phone_forms_keep_digits_only(raw: str, digits: str) -> None:
    parsed = parse_search(raw)
    assert parsed.mode == "phone"
    assert parsed.phone_digits == digits


def test_several_name_words_keep_their_order_independent_list() -> None:
    parsed = parse_search("  Ada   Lovelace ")
    assert parsed.mode == "name"
    assert parsed.name_words == ("ada", "lovelace")


def test_punctuation_is_a_literal_name_search() -> None:
    assert parse_search("***").name_words == ("***",)
    assert parse_search("%").name_words == ("%",)
    assert parse_search("100%").name_words == ("100%",)


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_pages_follow_the_name_then_the_number(api: TestClient) -> None:
    for number in range(1, 26):
        _create(api, f"Sample {number:02d}", f"90000000{number:02d}")
    first = api.get("/patients", cookies=_cookie(api))
    assert first.status_code == 200
    body = first.json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 25
    names = [item["full_name"] for item in body["items"]]
    assert names == [f"Sample {n:02d}" for n in range(1, 21)]

    second = api.get("/patients", cookies=_cookie(api), params={"page": 2})
    assert [item["full_name"] for item in second.json()["items"]] == [
        f"Sample {n:02d}" for n in range(21, 26)
    ]
    assert second.json()["total"] == 25

    past = api.get("/patients", cookies=_cookie(api), params={"page": 3})
    assert past.status_code == 200
    assert past.json()["items"] == []
    assert past.json()["total"] == 25

    wider = api.get("/patients", cookies=_cookie(api), params={"page_size": 100})
    assert len(wider.json()["items"]) == 25


def test_page_bounds_are_rejected(api: TestClient) -> None:
    cookie = _cookie(api)
    for params in ({"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": 101}):
        response = api.get("/patients", cookies=cookie, params=params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        assert (
            str(params["page"] if "page" in params else params["page_size"])
            not in (response.json()["error"]["message"])
        )


def test_name_search_is_case_insensitive_and_requires_every_word(api: TestClient) -> None:
    _create(api, "Ada Lovelace", "9000000003")
    _create(api, "Ada", "9000000004")
    _create(api, "Grace Lovelace", "9000000005")
    found = api.get("/patients", cookies=_cookie(api), params={"q": "  lovelace ADA "})
    assert found.status_code == 200
    assert [item["full_name"] for item in found.json()["items"]] == ["Ada Lovelace"]
    assert found.json()["total"] == 1
    blank = api.get("/patients", cookies=_cookie(api), params={"q": "   "})
    assert blank.json()["total"] == 3


def test_phone_search_finds_the_same_patient_from_each_form(api: TestClient) -> None:
    _create(api, "Sample Ada", "+91 98765 43210")
    _create(api, "Sample Bea", "9000000003")
    cookie = _cookie(api)
    for raw in ("98765", "+91 98765 43210", "(98765) 43210"):
        found = api.get("/patients", cookies=cookie, params={"q": raw})
        assert [item["full_name"] for item in found.json()["items"]] == ["Sample Ada"]
        assert found.json()["total"] == 1


def test_a_percent_sign_does_not_match_every_name(api: TestClient) -> None:
    _create(api, "100% Sample", "9000000099")
    _create(api, "Other Sample", "9000000098")
    cookie = _cookie(api)
    found = api.get("/patients", cookies=cookie, params={"q": "100%"})
    assert [item["full_name"] for item in found.json()["items"]] == ["100% Sample"]
    literal = api.get("/patients", cookies=cookie, params={"q": "%"})
    assert [item["full_name"] for item in literal.json()["items"]] == ["100% Sample"]


def test_patient_id_matches_one_number_and_not_a_phone(api: TestClient) -> None:
    for number in range(1, 12):
        _create(api, f"Sample {number:02d}", f"90000030{number:02d}")
    created = _create(api, "Token Twelve", "9000000007")
    _create(api, "Phone Twelve", "9000000012")
    assert created["display_id"] == "P-0012"
    cookie = _cookie(api)
    for raw in ("12", "P-0012", "p0012", "p-12"):
        found = api.get("/patients", cookies=cookie, params={"q": raw})
        assert [item["display_id"] for item in found.json()["items"]] == ["P-0012"]
        assert found.json()["total"] == 1


def test_an_id_search_does_not_cross_clinics(api: TestClient) -> None:
    _create(api, "Sample Ada", "9000000003")
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        actor = create_user(
            session,
            other.id,
            "other@x.test",
            "Synthetic Person",
            "synthetic-password-marker",
            ["receptionist"],
        )
        register_patient(session, other.id, actor.id, "Sample Bea", "9000000004", None)
        session.commit()
    cookie = _cookie(api)
    found = api.get("/patients", cookies=cookie, params={"q": "P-0001"})
    assert [item["full_name"] for item in found.json()["items"]] == ["Sample Ada"]
    other_cookie = {"dc_session": login(api, "other@x.test")}
    theirs = api.get("/patients", cookies=other_cookie, params={"q": "P-0001"})
    assert [item["full_name"] for item in theirs.json()["items"]] == ["Sample Bea"]


def _cookie(api: TestClient) -> dict[str, str]:
    return {"dc_session": login(api, "receptionist@x.test")}


def _create(api: TestClient, name: str, phone: str) -> dict[str, object]:
    response = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": name, "phone": phone},
    )
    assert response.status_code == 201
    body: dict[str, object] = response.json()
    return body
