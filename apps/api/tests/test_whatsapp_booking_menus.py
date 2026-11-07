"""Patient menu pages remain readable and never silently lose a choice."""

from dentacircle.domain.whatsapp_booking import menu_page, parse_menu_command


def test_pages_show_every_entry_with_current_codes() -> None:
    entries = [f"Choice {i}" for i in range(23)]
    cursor = 0
    seen: list[str] = []
    while cursor < len(entries):
        page = menu_page("Choose", entries, cursor, "AB12")
        assert len(page.text) <= 2000
        assert 1 <= len(page.entries) <= 5
        for index, entry in enumerate(page.entries, start=1):
            assert f"AB12:{index} {entry}" in page.text
        seen.extend(page.entries)
        cursor = page.next_cursor
    assert seen == entries


def test_long_labels_fit_without_ambiguous_codes() -> None:
    page = menu_page("Choose", ["A" * 4000, "Other"], 0, "AB12")
    assert len(page.text) <= 2000
    assert page.next_cursor > 0
    assert "AB12:1 " in page.text
    assert page.entries[0] == "A" * 4000


def test_only_current_token_can_select_or_page() -> None:
    assert parse_menu_command("ab12:2", "AB12", 3) == ("select", 1)
    assert parse_menu_command("MORE AB12", "AB12", 3) == ("more", None)
    assert parse_menu_command("OLD1:2", "AB12", 3) == ("invalid", None)
    assert parse_menu_command("AB12:4", "AB12", 3) == ("invalid", None)
    assert parse_menu_command("2", "AB12", 3) == ("invalid", None)
    assert parse_menu_command("I need help", "AB12", 3) == ("text", None)
