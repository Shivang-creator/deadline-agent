"""Scheduler correctness: fires at the right thresholds, never double-fires,
respects the daily digest's once-per-day gate, and produces nothing when
nobody has ever connected a channel."""

from __future__ import annotations

from datetime import UTC, timedelta

from deadline_agent.core.db import Database
from deadline_agent.core.scheduler import digest, tick


def _add(db, clock, name, in_):
    return db.add_deadline(name, clock.now() + in_, clock.now(), "fake")


def test_no_notifications_with_no_channel_bindings(db: Database, clock):
    _add(db, clock, "Solo", timedelta(hours=1))
    assert tick(db, clock) == []


def test_thresholds_fire_when_deadline_added_close_to_due(db: Database, clock):
    # Added with only 45 minutes left: the 24h and 6h trigger points are
    # already behind "now", same as the 1h one, so all three become
    # eligible on the very first tick (see the "catch-up" test below for
    # why that's the correct behavior, not a bug).
    db.upsert_channel_binding("telegram", "conv-1", "alice", clock.now())
    deadline = _add(db, clock, "Soon", timedelta(minutes=45))

    notifications = tick(db, clock)
    assert {n.kind for n in notifications} == {"alert:24h", "alert:6h", "alert:1h"}
    assert all(n.deadline_id == deadline.id for n in notifications)
    assert all(n.channel == "telegram" and n.conversation_id == "conv-1" for n in notifications)


def test_repeated_tick_never_resends_the_same_threshold(db: Database, clock):
    db.upsert_channel_binding("telegram", "conv-1", "alice", clock.now())
    _add(db, clock, "Soon", timedelta(minutes=45))

    first = tick(db, clock)
    second = tick(db, clock)
    assert len(first) == 3  # the catch-up burst, one notification per threshold
    assert second == []  # nothing left to notify — no duplicates


def test_three_thresholds_fire_in_sequence_as_clock_advances(db: Database, clock):
    db.upsert_channel_binding("telegram", "conv-1", "alice", clock.now())
    _add(db, clock, "Big Deadline", timedelta(hours=25))

    assert tick(db, clock) == []  # 25h out: too early for even the 24h alert

    clock.advance(hours=1, minutes=1)  # ~23h59m out -> past the 24h trigger
    fired = tick(db, clock)
    assert [n.kind for n in fired] == ["alert:24h"]

    assert tick(db, clock) == []  # no repeat on the same threshold

    clock.advance(hours=18)  # ~5h59m out -> past the 6h trigger
    fired = tick(db, clock)
    assert [n.kind for n in fired] == ["alert:6h"]

    clock.advance(hours=5, minutes=1)  # ~59m out -> past the 1h trigger
    fired = tick(db, clock)
    assert [n.kind for n in fired] == ["alert:1h"]

    clock.advance(hours=2)  # now past due entirely
    assert tick(db, clock) == []  # no more "before" alerts once it's overdue


def test_catch_up_fires_multiple_thresholds_at_once_if_all_are_already_due(db: Database, clock):
    # Deadline added with only 30 minutes left: the 24h and 6h trigger
    # points are already in the past relative to "now", so both fire
    # alongside the 1h alert on the very next tick. This is intentional —
    # see scheduler.py's docstring — and is also how a near-future test
    # deadline proves live delivery works once real tokens are wired in.
    db.upsert_channel_binding("discord", "conv-9", "bob", clock.now())
    _add(db, clock, "Rush", timedelta(minutes=30))

    fired = tick(db, clock)
    assert {n.kind for n in fired} == {"alert:24h", "alert:6h", "alert:1h"}


def test_alert_sent_to_every_known_channel_binding(db: Database, clock):
    db.upsert_channel_binding("telegram", "conv-1", "alice", clock.now())
    db.upsert_channel_binding("discord", "conv-9", "alice#0001", clock.now())
    _add(db, clock, "Soon", timedelta(minutes=45))

    fired = tick(db, clock)
    channels = {(n.channel, n.conversation_id) for n in fired}
    assert channels == {("telegram", "conv-1"), ("discord", "conv-9")}


def test_digest_does_not_fire_before_configured_hour(db: Database, clock):
    # REFERENCE_NOW is 17:30 IST — after the default 9am gate — so force an
    # early-morning clock (03:00 UTC = 08:30 IST) to check the gate itself.
    from datetime import datetime

    db.upsert_channel_binding("telegram", "conv-1", "alice", clock.now())
    clock.set(datetime(2026, 8, 17, 3, 0, tzinfo=UTC))
    assert digest(db, clock) == []


def test_digest_fires_once_per_day_and_not_again_same_day(db: Database, clock):
    db.upsert_channel_binding("telegram", "conv-1", "alice", clock.now())
    _add(db, clock, "Open Thing", timedelta(days=2))

    first = digest(db, clock)
    assert len(first) == 1
    assert first[0].kind == "digest"
    assert "Open Thing" in first[0].text

    assert digest(db, clock) == []  # same day -> gated

    clock.advance(days=1)
    second = digest(db, clock)
    assert len(second) == 1  # new day -> fires again


def test_digest_lists_only_open_deadlines(db: Database, clock):
    db.upsert_channel_binding("telegram", "conv-1", "alice", clock.now())
    _add(db, clock, "AlreadyPast", timedelta(minutes=-5))
    _add(db, clock, "StillOpen", timedelta(days=1))

    [n] = digest(db, clock)
    assert "StillOpen" in n.text
    assert "AlreadyPast" not in n.text


def test_digest_with_no_open_deadlines_says_so(db: Database, clock):
    db.upsert_channel_binding("telegram", "conv-1", "alice", clock.now())
    [n] = digest(db, clock)
    assert "nothing open" in n.text.lower()
