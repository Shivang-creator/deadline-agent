from __future__ import annotations

from datetime import UTC, datetime

from deadline_agent.core.parser import parse_datetime

NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)  # Sun 16 Aug, 17:30 IST


def test_iso_timestamp():
    result = parse_datetime("2026-08-20T18:30:00+05:30", now=NOW)
    assert result is not None
    assert result.astimezone(UTC).isoformat() == "2026-08-20T13:00:00+00:00"


def test_relative_in_hours():
    result = parse_datetime("in 6 hours", now=NOW)
    assert result is not None
    delta = result - NOW
    assert abs(delta.total_seconds() - 6 * 3600) < 60  # within a minute


def test_relative_tomorrow_with_time():
    result = parse_datetime("tomorrow 3am", now=NOW)
    assert result is not None
    local = result.astimezone(tz=__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    assert local.date().isoformat() == "2026-08-17"
    assert local.hour == 3


def test_day_month_time_prefers_future():
    # "16 Aug 9pm" — 16 Aug is TODAY relative to NOW (17:30 IST) but 9pm IST
    # is still later today, so this should resolve to today, not next year.
    result = parse_datetime("16 Aug 9pm", now=NOW)
    assert result is not None
    local = result.astimezone(tz=__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    assert local.year == 2026
    assert local.month == 8
    assert local.day == 16
    assert local.hour == 21


def test_ambiguous_date_prefers_future_not_past():
    # "1 Jan" with no year, relative to 16 Aug 2026, should resolve forward
    # to Jan 2027 (the future), not backward to Jan 2026 (the past).
    result = parse_datetime("1 Jan 9am", now=NOW)
    assert result is not None
    assert result > NOW


def test_garbage_returns_none():
    assert parse_datetime("asdkjfh not a date at all", now=NOW) is None


def test_empty_returns_none():
    assert parse_datetime("", now=NOW) is None
    assert parse_datetime("   ", now=NOW) is None


def test_in_minutes():
    result = parse_datetime("in 90 minutes", now=NOW)
    assert result is not None
    delta = result - NOW
    assert abs(delta.total_seconds() - 90 * 60) < 60


def test_bare_weekday_name():
    # A bare weekday ("friday 6pm") resolves to the next occurrence.
    result = parse_datetime("friday 6pm", now=NOW)
    assert result is not None
    assert result > NOW


def test_relative_in_days():
    result = parse_datetime("in 2 days", now=NOW)
    assert result is not None
    delta = result - NOW
    assert abs(delta.total_seconds() - 2 * 86400) < 60


def test_known_limitation_next_weekday_phrasing_unsupported():
    # Documented limitation: the underlying `dateparser` library does not
    # resolve the "next <weekday>" phrasing in this configuration (verified
    # against dateparser 1.4.2) — only a bare weekday name ("friday 6pm",
    # tested above) or an explicit date. None is the correct, honest result;
    # handler.py turns a None into a "couldn't find a date" reply rather
    # than guessing.
    assert parse_datetime("next monday 9am", now=NOW) is None
