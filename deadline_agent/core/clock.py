"""Time source for the core.

Every module that needs "now" takes a Clock instead of calling
datetime.now()/utcnow() directly. That is what makes the scheduler testable:
tests hand it a FakeClock and move time forward by minutes or days without
sleeping, while production wiring hands it the real SystemClock. Nothing in
core/ ever reads the wall clock on its own.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


class Clock:
    """Protocol: anything with a zero-arg now() -> aware UTC datetime."""

    def now(self) -> datetime:  # pragma: no cover - interface only
        raise NotImplementedError


class SystemClock(Clock):
    """The real clock. Used by both the fake-channel runner and the live
    Caspian app — it is not channel-specific, just not-fake."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock(Clock):
    """A clock tests (and the interactive fake-channel demo) can advance by
    hand. Starts at the given time, or 2026-08-16T12:00:00Z if none given."""

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)
        if self._now.tzinfo is None:
            self._now = self._now.replace(tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> datetime:
        """Move time forward by a timedelta (advance(hours=6), advance(minutes=90), ...)."""
        self._now = self._now + timedelta(**kwargs)
        return self._now

    def set(self, dt: datetime) -> None:
        self._now = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
