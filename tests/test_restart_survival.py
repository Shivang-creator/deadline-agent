"""Proves alerts survive a process restart without re-firing ones already
sent: "restart" is simulated by closing the Database and opening a brand
new Database object against the same SQLite file — nothing in memory
carries over, only what's on disk."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from deadline_agent.core.clock import FakeClock
from deadline_agent.core.db import Database
from deadline_agent.core.scheduler import digest, tick

from .conftest import REFERENCE_NOW


def test_alert_not_resent_after_restart(tmp_path: Path):
    db_path = tmp_path / "restart.db"
    clock = FakeClock(REFERENCE_NOW)

    db1 = Database(db_path)
    db1.upsert_channel_binding("telegram", "conv-1", "alice", clock.now())
    db1.add_deadline("Soon", clock.now() + timedelta(minutes=45), clock.now(), "fake")
    fired_before_restart = tick(db1, clock)
    assert len(fired_before_restart) == 3  # 24h/6h/1h catch-up burst
    db1.close()  # "process exits"

    # "process restarts": a fresh Database instance, same file, same clock time.
    db2 = Database(db_path)
    fired_after_restart = tick(db2, clock)
    assert fired_after_restart == []  # nothing re-sent
    db2.close()


def test_notified_thresholds_persist_across_restart_even_as_time_advances(tmp_path: Path):
    db_path = tmp_path / "restart2.db"
    clock = FakeClock(REFERENCE_NOW)

    db1 = Database(db_path)
    db1.upsert_channel_binding("discord", "conv-9", "bob", clock.now())
    deadline = db1.add_deadline(
        "Big Thing", clock.now() + timedelta(hours=25), clock.now(), "fake"
    )
    assert tick(db1, clock) == []  # 25h out: nothing due yet
    clock.advance(hours=2)  # ~23h out -> past the 24h trigger
    fired = tick(db1, clock)
    assert [n.kind for n in fired] == ["alert:24h"]
    db1.close()

    db2 = Database(db_path)
    # Same threshold must not re-fire on the reopened db, even though the
    # clock keeps advancing and other thresholds become newly eligible.
    clock.advance(hours=17)  # ~6h out -> past the 6h trigger only
    fired2 = tick(db2, clock)
    assert [n.kind for n in fired2] == ["alert:6h"]
    assert db2.has_notified(deadline.id, "alert:24h") is True
    db2.close()


def test_digest_log_persists_across_restart(tmp_path: Path):
    db_path = tmp_path / "restart3.db"
    clock = FakeClock(REFERENCE_NOW)

    db1 = Database(db_path)
    db1.upsert_channel_binding("telegram", "conv-1", "alice", clock.now())
    db1.add_deadline("Open Thing", clock.now() + timedelta(days=2), clock.now(), "fake")
    first = digest(db1, clock)
    assert len(first) == 1
    db1.close()

    db2 = Database(db_path)
    assert digest(db2, clock) == []  # same day, already sent - even after restart
    db2.close()
