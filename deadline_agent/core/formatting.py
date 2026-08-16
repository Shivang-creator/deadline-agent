"""Human-readable rendering of times and durations. Pure functions, no I/O."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DISPLAY_TIMEZONE = "Asia/Kolkata"


def format_dt(dt: datetime, timezone_name: str = DISPLAY_TIMEZONE) -> str:
    local = dt.astimezone(ZoneInfo(timezone_name))
    return local.strftime("%a %d %b %Y, %I:%M %p %Z")


def format_timedelta(delta: timedelta) -> str:
    """"2d 3h", "45m", "3h 12m" — always shows minutes, hours+minutes past
    the 1h mark, days+hours past the 1d mark. Never a negative sign; callers
    decide how to label a negative delta (e.g. "OVERDUE by ...")."""
    total_seconds = int(abs(delta.total_seconds()))
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
