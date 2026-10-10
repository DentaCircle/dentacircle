"""Patient field rules, display ids, and how a search box is read.

Search is plain "contains". There is no trigram index.

`q` is one of these, after trimming:

- Blank: no filter.
- A patient id: `P-0012`, `p0012`, `p-12`, or a bare number of 1 to 4 digits (`12`,
  `0012`). These match that patient number exactly. `P-10000` is still an id.
- A phone: 5 or more digits, or digits mixed with spaces, `+`, `-`, `(` and `)`.
  Matching uses the digits only, and "contains". `98765` is a phone, not patient 98765.
  A bare 5-digit-or-longer number is a phone so a short id search does not also match
  most phone numbers. `10000` is a phone; use `P-10000` for that id.
- A name: any other text. Each whitespace-separated word must appear in the name,
  ignoring case. A word may appear in any order. `%` is a literal character.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

MAX_NAME_LENGTH = 200
MAX_PHONE_LENGTH = 30
MIN_PHONE_DIGITS = 7
MAX_PHONE_DIGITS = 15
MIN_DATE_OF_BIRTH = date(1900, 1, 1)
# Display ids are padded to 4 digits, so a bare number that long is an id.
# Longer bare numbers are phone fragments. See the module docstring.
_BARE_ID_MAX_DIGITS = 4
_PHONE_CHARS = set("0123456789+-() ")
# patient_number is a PostgreSQL integer. A larger id search must not reach the query.
_MAX_PATIENT_NUMBER = 2_147_483_647

PATIENT_ROLES = ("receptionist", "clinician", "clinic_admin")


class PatientFieldError(Exception):
    """One field failed a rule. `code` is a validation name and carries no submitted value."""

    def __init__(self, field: str, code: str) -> None:
        self.field = field
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SearchFilter:
    mode: Literal["all", "none", "name", "phone", "number"]
    name_words: tuple[str, ...] = ()
    phone_digits: str = ""
    patient_number: int | None = None


def display_id(patient_number: int) -> str:
    return f"P-{patient_number:04d}"


def clean_name(name: str) -> str:
    trimmed = name.strip()
    if not trimmed:
        raise PatientFieldError("full_name", "string_too_short")
    if len(trimmed) > MAX_NAME_LENGTH:
        raise PatientFieldError("full_name", "string_too_long")
    return trimmed


def clean_phone(phone: str) -> tuple[str, str]:
    """Return the trimmed phone as entered, and its digits.

    A leading `+` is kept in the stored phone and dropped from the digits.
    Spaces, `-`, `(` and `)` are kept in the stored phone and dropped from the digits.
    """
    trimmed = phone.strip()
    if not trimmed:
        raise PatientFieldError("phone", "string_too_short")
    if len(trimmed) > MAX_PHONE_LENGTH:
        raise PatientFieldError("phone", "string_too_long")
    body = trimmed[1:] if trimmed.startswith("+") else trimmed
    digits: list[str] = []
    for char in body:
        if char.isdigit():
            digits.append(char)
            continue
        if char in " -()":
            continue
        raise PatientFieldError("phone", "phone_digits")
    phone_digits = "".join(digits)
    if len(phone_digits) < MIN_PHONE_DIGITS or len(phone_digits) > MAX_PHONE_DIGITS:
        raise PatientFieldError("phone", "phone_digits")
    return trimmed, phone_digits


def check_date_of_birth(value: date | None, today: date) -> None:
    """`today` is the clinic's local date. A missing date is allowed."""
    if value is None:
        return
    if value < MIN_DATE_OF_BIRTH:
        raise PatientFieldError("date_of_birth", "date_before_min")
    if value > today:
        raise PatientFieldError("date_of_birth", "date_future")


def parse_search(raw: str | None) -> SearchFilter:
    if raw is None or raw.strip() == "":
        return SearchFilter("all")
    trimmed = raw.strip()
    prefixed = _prefixed_id(trimmed)
    if prefixed is not None:
        return SearchFilter("number", patient_number=prefixed)
    if trimmed.isdigit():
        if len(trimmed) <= _BARE_ID_MAX_DIGITS:
            return SearchFilter("number", patient_number=int(trimmed))
        return SearchFilter("phone", phone_digits=trimmed)
    if _is_phone_text(trimmed):
        digits = "".join(char for char in trimmed if char.isdigit())
        return SearchFilter("phone", phone_digits=digits)
    words = tuple(word.casefold() for word in trimmed.split() if word)
    if not words:
        return SearchFilter("none")
    return SearchFilter("name", name_words=words)


def _prefixed_id(trimmed: str) -> int | None:
    if not trimmed or trimmed[0] not in "Pp":
        return None
    rest = trimmed[1:]
    if rest.startswith("-"):
        rest = rest[1:]
    if not rest.isdigit():
        return None
    number = int(rest)
    if number > _MAX_PATIENT_NUMBER:
        return None
    return number


def _is_phone_text(trimmed: str) -> bool:
    if not any(char.isdigit() for char in trimmed):
        return False
    return all(char in _PHONE_CHARS for char in trimmed)
