"""Small, deterministic menu primitives for patient booking messages."""

import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MenuPage:
    text: str
    entries: list[str]
    next_cursor: int


def menu_page(title: str, entries: list[str], cursor: int, token: str) -> MenuPage:
    """Display at most five choices, retaining full labels for the selected summary."""
    if not 0 <= cursor <= len(entries) or not re.fullmatch(r"[A-Z0-9]{4,12}", token):
        raise ValueError("invalid menu cursor or token")
    labels = entries[cursor : cursor + 5]
    lines = [title[:300]]
    for index, label in enumerate(labels, start=1):
        clean = " ".join(label.split())
        display = clean if len(clean) <= 300 else clean[:299] + "…"
        lines.append(f"{token}:{index} {display}")
    next_cursor = cursor + len(labels)
    if next_cursor < len(entries):
        lines.append(f"More choices: MORE {token}")
    lines.append("For reception, reply STAFF. To stop, reply STOP.")
    message = "\n".join(lines)
    if len(message) > 2000:
        raise ValueError("menu text exceeds limit")
    return MenuPage(message, labels, next_cursor)


def parse_menu_command(
    value: str, token: str, count: int
) -> tuple[Literal["select", "more", "invalid", "text"], int | None]:
    """Do not reinterpret an old code as a new choice."""
    command = value.strip().upper()
    if command.isdigit():
        return "invalid", None
    if re.fullmatch(r"MORE(?:\s+\S+)?", command):
        return ("more", None) if command == f"MORE {token}" else ("invalid", None)
    match = re.fullmatch(r"([A-Z0-9]+):(\d+)", command)
    if match:
        index = int(match.group(2)) - 1
        if match.group(1) == token and 0 <= index < count:
            return "select", index
        return "invalid", None
    return "text", None
