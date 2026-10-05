from dentacircle.core.security import (
    hash_password,
    hash_token,
    new_session_token,
    verify_dummy_password,
    verify_password,
)

_MARKER = "synthetic-password-marker"


def test_a_password_verifies_against_its_own_hash() -> None:
    stored = hash_password(_MARKER)
    assert stored != _MARKER
    assert verify_password(stored, _MARKER) is True


def test_a_different_password_does_not_verify() -> None:
    stored = hash_password(_MARKER)
    assert verify_password(stored, "other-synthetic-password") is False


def test_the_hash_is_argon2id() -> None:
    assert hash_password(_MARKER).startswith("$argon2id$")


def test_dummy_verification_accepts_anything() -> None:
    verify_dummy_password(_MARKER)
    verify_dummy_password("anything")


def test_tokens_are_unique_and_their_hash_hides_them() -> None:
    first = new_session_token()
    second = new_session_token()
    assert first != second
    assert hash_token(first) != first
    assert len(hash_token(first)) == 64
    assert hash_token(first) == hash_token(first)
