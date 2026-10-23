"""Document rules: allowed types, size limit, filename cleaning and the file-type check.

Everything here is pure. The database check constraints list the same types and limits.
"""

import unicodedata
from urllib.parse import quote, unquote

DOCUMENT_READ_ROLES = ("clinician", "receptionist", "clinic_admin")
DOCUMENT_WRITE_ROLES = ("clinician", "receptionist", "clinic_admin")

PDF = "application/pdf"
PNG = "image/png"
JPEG = "image/jpeg"
DOCUMENT_CONTENT_TYPES = (PDF, PNG, JPEG)

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_FILENAME_LENGTH = 200
DOCUMENT_FILENAME_HEADER = "X-Document-Filename"


def decode_filename_header(value: str) -> str:
    """The original name after UTF-8 percent-decoding from the upload header."""
    return unquote(value, encoding="utf-8")


# The first bytes of each allowed type. The browser's Content-Type is never trusted alone.
_SIGNATURES = (
    (b"%PDF-", PDF),
    (b"\x89PNG\r\n\x1a\n", PNG),
    (b"\xff\xd8\xff", JPEG),
)
# Control, format (such as right-to-left overrides) and line or paragraph separators.
_REMOVED_CATEGORIES = frozenset(("Cc", "Cf", "Zl", "Zp"))


class DocumentFieldError(Exception):
    """One input failed a rule. `code` is a validation name and carries no submitted value."""

    def __init__(self, location: str, code: str) -> None:
        self.location = location
        self.code = code
        super().__init__(code)


class UnsupportedMediaTypeError(Exception):
    """The bytes are not a PDF, PNG or JPEG, or the Content-Type disagrees with them."""


def sniff_content_type(data: bytes) -> str | None:
    """The allowed type the first bytes announce, or None."""
    for signature, content_type in _SIGNATURES:
        if data.startswith(signature):
            return content_type
    return None


def check_upload(data: bytes, declared_content_type: str | None) -> str:
    """The stored content type. An empty body is a field error, a type mismatch is not."""
    if not data:
        raise DocumentFieldError("body", "string_too_short")
    sniffed = sniff_content_type(data)
    if sniffed is None or _media_type(declared_content_type) != sniffed:
        raise UnsupportedMediaTypeError
    return sniffed


def clean_filename(raw: str) -> str:
    """A label for the file: no folders, no control characters, 1 to 200 characters."""
    kept = "".join(char for char in raw if unicodedata.category(char) not in _REMOVED_CATEGORIES)
    name = kept.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name:
        raise DocumentFieldError("filename", "string_too_short")
    if len(name) > MAX_FILENAME_LENGTH:
        raise DocumentFieldError("filename", "string_too_long")
    return name


IMAGE_INLINE_CSP = "sandbox; default-src 'none'"


def content_disposition(disposition: str, filename: str) -> str:
    """Content-Disposition for a download or an inline view. The name is only a label."""
    fallback = "".join(
        char if char.isascii() and char.isprintable() and char not in '"\\%' else "_"
        for char in filename
    )
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def attachment_disposition(filename: str) -> str:
    """Content-Disposition for a download. The name is only a label, never a path."""
    return content_disposition("attachment", filename)


def is_inline_image(content_type: str) -> bool:
    """PNG and JPEG are shown with a sandbox policy. PDF is not."""
    return content_type in (PNG, JPEG)


def _media_type(header: str | None) -> str:
    if header is None:
        return ""
    return header.split(";", 1)[0].strip().lower()
