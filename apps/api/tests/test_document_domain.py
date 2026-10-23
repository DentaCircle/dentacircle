"""Document rules: file-type check, upload check, filename cleaning and the download header."""

import pytest

from dentacircle.domain.document import (
    JPEG,
    MAX_DOCUMENT_BYTES,
    MAX_FILENAME_LENGTH,
    PDF,
    PNG,
    DocumentFieldError,
    UnsupportedMediaTypeError,
    attachment_disposition,
    check_upload,
    clean_filename,
    sniff_content_type,
)

_PDF = b"%PDF-1.7\nsynthetic"
_PNG = b"\x89PNG\r\n\x1a\nsynthetic"
_JPEG = b"\xff\xd8\xff\xe0synthetic"


def test_the_limit_is_eight_mebibytes() -> None:
    assert MAX_DOCUMENT_BYTES == 8_388_608


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (_PDF, PDF),
        (_PNG, PNG),
        (_JPEG, JPEG),
        (b"\xff\xd8\xff", JPEG),
        (b"", None),
        (b"%PDF", None),
        (b"GIF89a", None),
        (b"<html></html>", None),
        (b" %PDF-1.7", None),
        (b"\x89PNG\r\n", None),
        (b"MZ\x90\x00", None),
    ],
)
def test_the_type_comes_from_the_first_bytes(data: bytes, expected: str | None) -> None:
    assert sniff_content_type(data) == expected


def test_a_matching_header_gives_the_stored_type() -> None:
    assert check_upload(_PDF, "application/pdf") == PDF
    assert check_upload(_PNG, "image/png") == PNG
    assert check_upload(_JPEG, "image/jpeg") == JPEG


def test_the_header_is_compared_without_case_or_parameters() -> None:
    assert check_upload(_PDF, "Application/PDF") == PDF
    assert check_upload(_PNG, " image/png ; charset=binary") == PNG


@pytest.mark.parametrize(
    "declared", [None, "", "image/png", "application/octet-stream", "text/html"]
)
def test_a_header_that_disagrees_with_the_bytes_is_refused(declared: str | None) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        check_upload(_PDF, declared)


def test_the_bytes_decide_even_when_the_header_is_allowed() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        check_upload(b"<script>alert(1)</script>", "application/pdf")
    with pytest.raises(UnsupportedMediaTypeError):
        check_upload(b"GIF89a....", "image/gif")


def test_an_empty_body_is_a_field_error_not_a_type_error() -> None:
    with pytest.raises(DocumentFieldError) as caught:
        check_upload(b"", "application/pdf")
    assert caught.value.location == "body"
    assert caught.value.code == "string_too_short"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("  report.pdf  ", "report.pdf"),
        ("a/b\\c.pdf", "c.pdf"),
        ("C:\\scans\\xray.png", "xray.png"),
        ("../../etc/passwd", "passwd"),
        ("/abs/path/file.jpg", "file.jpg"),
        ("re\x00po\nrt\t.pdf", "report.pdf"),
        ("a\x00/b.pdf", "b.pdf"),
        ("evil\u202egnp.exe", "evilgnp.exe"),
        ("line\u2028break.pdf", "linebreak.pdf"),
        ("scan of ragi \u0c30\u0c3e\u0c17\u0c3f.pdf", "scan of ragi \u0c30\u0c3e\u0c17\u0c3f.pdf"),
        ("..", ".."),
        ("x" * MAX_FILENAME_LENGTH, "x" * MAX_FILENAME_LENGTH),
    ],
)
def test_filename_cleaning(raw: str, expected: str) -> None:
    assert clean_filename(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "\x00\x01", "folder/", "a/b\\", "/", "\u202e"])
def test_a_name_that_is_empty_after_cleaning_is_refused(raw: str) -> None:
    with pytest.raises(DocumentFieldError) as caught:
        clean_filename(raw)
    assert caught.value.location == "filename"
    assert caught.value.code == "string_too_short"


def test_a_name_over_the_limit_after_cleaning_is_refused() -> None:
    with pytest.raises(DocumentFieldError) as caught:
        clean_filename("x" * (MAX_FILENAME_LENGTH + 1))
    assert caught.value.code == "string_too_long"
    assert clean_filename("folder/" + "x" * MAX_FILENAME_LENGTH) == "x" * MAX_FILENAME_LENGTH


def test_cleaning_twice_changes_nothing() -> None:
    once = clean_filename(" a/b\\ re\x00port.pdf ")
    assert clean_filename(once) == once


def test_the_download_header_is_an_attachment_with_a_safe_name() -> None:
    header = attachment_disposition("report.pdf")
    assert header == "attachment; filename=\"report.pdf\"; filename*=UTF-8''report.pdf"


def test_the_download_header_cannot_be_broken_by_the_name() -> None:
    header = attachment_disposition('a"b\\c%d\r\ne;f.pdf')
    assert header.startswith('attachment; filename="a_b_c_d__e;f.pdf"')
    assert "\r" not in header
    assert "\n" not in header
    assert header.count('"') == 2
    encoded = header.split("filename*=UTF-8''", 1)[1]
    assert encoded.isascii()
    assert "%22" in encoded
    assert "%0D%0A" in encoded


def test_a_non_ascii_name_has_an_ascii_fallback() -> None:
    header = attachment_disposition("r\u00e9sum\u00e9.pdf")
    assert 'filename="r_sum_.pdf"' in header
    assert "filename*=UTF-8''r%C3%A9sum%C3%A9.pdf" in header
