"""OpenWA events must not turn unsupported traffic into patient messages."""

from dentacircle.integrations.messaging.openwa import OpenWaMessagingProvider


def event(**changes: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": "message-1",
        "from": "15551234567@c.us",
        "body": " Hello ",
        "type": "chat",
        "isGroupMsg": False,
        "fromMe": False,
        "t": 1700000000,
    }
    data.update(changes)
    return {"sessionId": "demo", "event": "onMessage", "data": data}


def provider() -> OpenWaMessagingProvider:
    return OpenWaMessagingProvider("http://localhost:8080", "key", "demo")


def test_direct_text_is_normalized() -> None:
    result = provider().normalize_event(event())
    assert result is not None
    assert (result.number, result.body, result.provider_message_id) == (
        "+15551234567",
        "Hello",
        "message-1",
    )
    assert result.account_key == "demo"
    assert result.provider_sent_at is not None


def test_direct_text_preserves_valid_quoted_message_reference() -> None:
    result = provider().normalize_event(event(quotedStanzaID="ABC123"))
    assert result is not None
    assert result.quoted_stanza_id == "ABC123"
    invalid = provider().normalize_event(event(quotedStanzaID="bad reference!"))
    assert invalid is not None
    assert invalid.quoted_stanza_id is None


def test_unsupported_events_are_ignored() -> None:
    for changes in (
        {"from": "123@g.us"},
        {"isGroupMsg": True},
        {"fromMe": True},
        {"fromMe": None},
        {"isGroupMsg": None},
        {"type": "image"},
        {"body": " "},
        {"body": "x" * 2001},
    ):
        assert provider().normalize_event(event(**changes)) is None
    wrong_session = event()
    wrong_session["sessionId"] = "other"
    assert provider().normalize_event(wrong_session) is None


def test_lid_sender_requires_matching_contact_identity() -> None:
    sender = {"lid": "123456789@lid", "phoneNumber": "15551234567@c.us"}
    result = provider().normalize_event(event(**{"from": "123456789@lid", "sender": sender}))
    assert result is not None
    assert result.number == "+15551234567"
    for invalid in (
        {"lid": "999@lid", "phoneNumber": "15551234567@c.us"},
        {"lid": "123456789@lid", "phoneNumber": "123@g.us"},
        {"lid": "123456789@lid"},
    ):
        assert (
            provider().normalize_event(event(**{"from": "123456789@lid", "sender": invalid}))
            is None
        )


def test_send_uses_v4_argument_envelope_and_session_guard(monkeypatch: object) -> None:
    import json
    from unittest.mock import patch

    class Reply:
        def __enter__(self) -> "Reply":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self) -> bytes:
            return b'{"success": true, "response": "true_message_id"}'

    with patch("dentacircle.integrations.messaging.openwa.urlopen", return_value=Reply()) as call:
        assert provider().send_text("+15551234567", "Hello") == "accepted"
        request = call.call_args.args[0]
        assert json.loads(request.data) == {"args": {"to": "15551234567@c.us", "content": "Hello"}}
        assert request.get_header("Owa-check-value") == "demo"


def test_send_receipt_keeps_provider_reference() -> None:
    from unittest.mock import patch

    bridge = provider()
    with patch.object(bridge, "_call", return_value={"response": "true_chat_STANZA123"}):
        receipt = bridge.send_text_receipt("+15551234567", "Hello")
    assert receipt.status == "accepted"
    assert receipt.provider_message_id == "true_chat_STANZA123"


def test_transport_failures_are_translated_without_provider_error_text() -> None:
    from http.client import HTTPMessage
    from unittest.mock import patch
    from urllib.error import HTTPError, URLError

    with patch(
        "dentacircle.integrations.messaging.openwa.urlopen", side_effect=URLError("private")
    ):
        assert provider().connection().status == "disconnected"
        assert provider().send_text("+15551234567", "Hello") == "unknown"
    rejection = HTTPError("http://localhost", 400, "private", HTTPMessage(), None)
    with patch("dentacircle.integrations.messaging.openwa.urlopen", side_effect=rejection):
        assert provider().send_text("+15551234567", "Hello") == "failed"
    outage = HTTPError("http://localhost", 503, "private", HTTPMessage(), None)
    with patch("dentacircle.integrations.messaging.openwa.urlopen", side_effect=outage):
        assert provider().send_text("+15551234567", "Hello") == "unknown"
