"""Proactive alerting: 24h/6h/1h-before thresholds, plus a once-daily digest.

Decoupled from any channel — it only knows about Deadlines and
ChannelBindings (both channel-agnostic records in the DB) and produces
Notification objects (channel + conversation_id + text) for the runtime loop
to actually deliver. "Already notified" state is persisted in the same
SQLite file as everything else, so a process restart never re-fires an alert
that already went out: tick()/digest() are pure functions of (db, now), and
they mark the DB *before* returning, in the same call that decided to fire.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .clock import Clock
from .db import Database
from .formatting import format_dt, format_timedelta
from .models import Deadline, Notification

THRESHOLDS: tuple[tuple[str, timedelta, str], ...] = (
    ("alert:24h", timedelta(hours=24), "24 hours"),
    ("alert:6h", timedelta(hours=6), "6 hours"),
    ("alert:1h", timedelta(hours=1), "1 hour"),
)

DIGEST_TIMEZONE = "Asia/Kolkata"
DIGEST_HOUR = 9  # local hour the daily digest is eligible to fire at


def tick(db: Database, clock: Clock) -> list[Notification]:
    """Check every open deadline against the 24h/6h/1h thresholds.

    A threshold fires once its trigger time (due_at - lead) has passed and
    the deadline itself hasn't, and it hasn't already been marked notified.
    Firing sends to every known channel binding — "wherever the user has
    been active" — and marks (deadline, threshold) notified immediately, so
    a second tick (or a fresh process re-reading the same DB file) never
    repeats it.
    """
    now = clock.now()
    notifications: list[Notification] = []
    bindings = db.list_channel_bindings()
    if not bindings:
        # Nobody has ever messaged the agent on any channel yet - nothing
        # to mark notified either, so the first real interaction still gets
        # a catch-up alert on the next tick if a threshold is already due.
        return notifications

    for deadline in db.list_deadlines():
        if deadline.due_at <= now:
            continue  # already due/passed - no more lead-time alerts
        for kind, lead, label in THRESHOLDS:
            if deadline.due_at - lead > now:
                continue  # too early for this threshold
            if db.has_notified(deadline.id, kind):
                continue
            text = _alert_text(deadline, now, label)
            notifications.extend(
                Notification(
                    channel=b.channel,
                    conversation_id=b.conversation_id,
                    text=text,
                    kind=kind,
                    deadline_id=deadline.id,
                )
                for b in bindings
            )
            db.mark_notified(deadline.id, kind, now)
    return notifications


def _alert_text(deadline: Deadline, now: datetime, label: str) -> str:
    remaining = format_timedelta(deadline.due_at - now)
    return (
        f'⏰ "{deadline.name}" is due in {remaining} '
        f"({format_dt(deadline.due_at)}) — this is the {label}-out alert."
    )


def digest(
    db: Database,
    clock: Clock,
    *,
    digest_hour: int = DIGEST_HOUR,
    timezone_name: str = DIGEST_TIMEZONE,
) -> list[Notification]:
    """Once-per-calendar-day summary of everything still open, sent after
    `digest_hour` local time. Restart-safe the same way tick() is: the date
    it last fired for is persisted, checked, and set in this same call."""
    now = clock.now()
    local = now.astimezone(ZoneInfo(timezone_name))
    if local.hour < digest_hour:
        return []
    digest_date = local.strftime("%Y-%m-%d")
    if db.has_digest_for(digest_date):
        return []
    bindings = db.list_channel_bindings()
    if not bindings:
        return []

    text = _digest_text(db.list_deadlines(), now)
    notifications = [
        Notification(
            channel=b.channel, conversation_id=b.conversation_id, text=text,
            kind="digest", deadline_id=None,
        )
        for b in bindings
    ]
    db.mark_digest_sent(digest_date, now)
    return notifications


def _digest_text(deadlines: list[Deadline], now: datetime) -> str:
    open_deadlines = [d for d in deadlines if d.due_at > now]
    if not open_deadlines:
        return "Daily digest: nothing open right now."
    lines = [f"Daily digest — {len(open_deadlines)} deadline(s) still open:"]
    for d in open_deadlines:
        lines.append(f"- {d.name} — {format_dt(d.due_at)} (in {format_timedelta(d.due_at - now)})")
    return "\n".join(lines)


def run_all(db: Database, clock: Clock) -> list[Notification]:
    """Convenience for the runtime loop and the fake-channel /tick command:
    both alert thresholds and the daily digest in one call."""
    return tick(db, clock) + digest(db, clock)
