"""Forgiving date/time parsing, isolated so it can be unit-tested on its own.

Wraps `dateparser` (a standard OSS library — not something built here) with
the settings that make it behave the way a judge typing quickly would expect:
- relative to "now" (the Clock's now, not the wall clock — testable)
- ambiguous dates ("17 Aug") resolve to the future, not the past
- no explicit timezone -> assumed to be the configured local timezone
  (defaults to Asia/Kolkata, since that's where this agent's user is)
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import dateparser

DEFAULT_TIMEZONE = "Asia/Kolkata"


def parse_datetime(
    text: str, *, now: datetime, timezone_name: str = DEFAULT_TIMEZONE
) -> datetime | None:
    """Parse a forgiving date/time phrase into an aware UTC datetime.

    Returns None if nothing date-like could be found. `now` anchors relative
    phrases ("in 6 hours", "tomorrow 3am") and must be an aware datetime.
    """
    text = (text or "").strip()
    if not text:
        return None

    local_now = now.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)
    settings = {
        "TIMEZONE": timezone_name,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": local_now,
    }
    result = dateparser.parse(text, settings=settings)
    if result is None:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=ZoneInfo(timezone_name))
    return result.astimezone(UTC)
