"""Translation between the pinned OpenWA v4 API and the messaging contract."""

import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dentacircle.integrations.messaging.base import (
    Connection,
    IncomingText,
    SendReceipt,
    SendStatus,
)

_ADDRESS = re.compile(r"^([1-9][0-9]{1,14})@c\.us$")
_LID = re.compile(r"^[0-9]+@lid$")


class OpenWaMessagingProvider:
    def __init__(self, base_url: str, api_key: str, account_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.account_key = account_key

    def _call(self, method: str, args: dict[str, str]) -> Any:
        request = Request(
            f"{self.base_url}/{method}",
            data=json.dumps({"args": args}).encode(),
            headers={
                "Content-Type": "application/json",
                "api_key": self.api_key,
                "owa-check-property": "session",
                "owa-check-value": self.account_key,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def connection(self) -> Connection:
        if not self.base_url or not self.api_key or not self.account_key:
            return Connection("unconfigured", False)
        try:
            result = self._call("isConnected", {})
        except (OSError, ValueError):
            return Connection("disconnected", False)
        connected = isinstance(result, dict) and result.get("response") is True
        return Connection("connected" if connected else "disconnected", connected)

    def send_text(self, number: str, body: str, *, fence_fd: int | None = None) -> SendStatus:
        return self.send_text_receipt(number, body).status

    def send_text_receipt(self, number: str, body: str) -> SendReceipt:
        try:
            result = self._call("sendText", {"to": number[1:] + "@c.us", "content": body})
        except HTTPError as exc:
            return SendReceipt("failed" if 400 <= exc.code < 500 else "unknown")
        except (URLError, OSError, ValueError):
            return SendReceipt("unknown")
        if not isinstance(result, dict):
            return SendReceipt("unknown")
        response = result.get("response")
        if response is False or (
            isinstance(response, str) and response.lower().startswith("error")
        ):
            return SendReceipt("failed")
        if result.get("success") is False:
            return SendReceipt("unknown")
        if response is True:
            return SendReceipt("accepted")
        if isinstance(response, str) and response:
            return SendReceipt("accepted", response)
        return SendReceipt("unknown")

    def normalize_event(self, payload: object) -> IncomingText | None:
        if not isinstance(payload, dict):
            raise ValueError("Malformed event")
        if not isinstance(payload.get("sessionId"), str) or not isinstance(
            payload.get("event"), str
        ):
            raise ValueError("Malformed event")
        if payload["sessionId"] != self.account_key or payload["event"] != "onMessage":
            return None
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("Malformed event")
        sender, body, message_id = data.get("from"), data.get("body"), data.get("id")
        if (
            data.get("fromMe") is not False
            or data.get("isGroupMsg") is not False
            or data.get("type") != "chat"
        ):
            return None
        if (
            not isinstance(sender, str)
            or not isinstance(body, str)
            or not isinstance(message_id, str)
        ):
            raise ValueError("Malformed event")
        address = _ADDRESS.fullmatch(sender)
        if address is None and _LID.fullmatch(sender):
            contact = data.get("sender")
            if isinstance(contact, dict) and contact.get("lid") == sender:
                phone = contact.get("phoneNumber")
                if isinstance(phone, str):
                    address = _ADDRESS.fullmatch(phone)
        body = body.strip()
        if not address or not 1 <= len(body) <= 2000 or not message_id:
            return None
        timestamp = data.get("t")
        sent_at = None
        if isinstance(timestamp, (int, float)):
            try:
                sent_at = datetime.fromtimestamp(timestamp, UTC)
            except (OverflowError, OSError, ValueError):
                pass
        quoted = data.get("quotedStanzaID")
        quoted_stanza_id = (
            quoted
            if isinstance(quoted, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", quoted)
            else None
        )
        return IncomingText(
            self.account_key, "+" + address.group(1), message_id, body, sent_at, quoted_stanza_id
        )
