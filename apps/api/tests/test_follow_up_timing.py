"""Due state is calculated from the stored date and clinic-local today."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from dentacircle.domain.follow_up import follow_up_timing

_ZONE = ZoneInfo("Asia/Kolkata")


def test_the_day_before_today_and_after() -> None:
    today = date(2026, 10, 21)
    assert follow_up_timing(date(2026, 10, 20), today) == "overdue"
    assert follow_up_timing(date(2026, 10, 21), today) == "due_today"
    assert follow_up_timing(date(2026, 10, 22), today) == "upcoming"


def test_clinic_local_today_can_differ_from_the_utc_day() -> None:
    """20:00 UTC on 20 Oct is 01:30 on 21 Oct in Asia/Kolkata."""
    now = datetime(2026, 10, 20, 20, 0, tzinfo=UTC)
    utc_day = now.astimezone(UTC).date()
    clinic_today = now.astimezone(_ZONE).date()
    assert utc_day == date(2026, 10, 20)
    assert clinic_today == date(2026, 10, 21)
    assert follow_up_timing(date(2026, 10, 20), clinic_today) == "overdue"
    assert follow_up_timing(date(2026, 10, 21), clinic_today) == "due_today"
    assert follow_up_timing(utc_day, clinic_today) == "overdue"
