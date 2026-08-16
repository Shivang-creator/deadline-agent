from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deadline_agent.core.db import Database

NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)


def test_add_and_list_deadline(db: Database):
    due = NOW + timedelta(days=1)
    deadline = db.add_deadline(name="OregonHacks", due_at=due, created_at=NOW, source_channel="fake")
    assert deadline.id is not None
    listed = db.list_deadlines()
    assert len(listed) == 1
    assert listed[0].name == "OregonHacks"
    assert listed[0].due_at == due


def test_list_sorted_soonest_first(db: Database):
    db.add_deadline("Later", NOW + timedelta(days=3), NOW, "fake")
    db.add_deadline("Sooner", NOW + timedelta(hours=2), NOW, "fake")
    db.add_deadline("Middle", NOW + timedelta(days=1), NOW, "fake")
    names = [d.name for d in db.list_deadlines()]
    assert names == ["Sooner", "Middle", "Later"]


def test_remove_deadline_excludes_from_default_list(db: Database):
    d = db.add_deadline("Gone", NOW + timedelta(days=1), NOW, "fake")
    db.remove_deadline(d.id, NOW)
    assert db.list_deadlines() == []
    assert len(db.list_deadlines(include_removed=True)) == 1


def test_get_deadline_by_id(db: Database):
    d = db.add_deadline("Findme", NOW + timedelta(days=1), NOW, "fake")
    fetched = db.get_deadline(d.id)
    assert fetched is not None
    assert fetched.name == "Findme"
    assert db.get_deadline(999999) is None


def test_notified_threshold_roundtrip(db: Database):
    d = db.add_deadline("X", NOW + timedelta(hours=2), NOW, "fake")
    assert db.has_notified(d.id, "alert:1h") is False
    db.mark_notified(d.id, "alert:1h", NOW)
    assert db.has_notified(d.id, "alert:1h") is True
    # A different threshold on the same deadline is independent.
    assert db.has_notified(d.id, "alert:6h") is False


def test_mark_notified_twice_is_idempotent(db: Database):
    d = db.add_deadline("X", NOW + timedelta(hours=2), NOW, "fake")
    db.mark_notified(d.id, "alert:1h", NOW)
    db.mark_notified(d.id, "alert:1h", NOW + timedelta(minutes=1))  # must not raise
    assert db.has_notified(d.id, "alert:1h") is True


def test_digest_log_roundtrip(db: Database):
    assert db.has_digest_for("2026-08-16") is False
    db.mark_digest_sent("2026-08-16", NOW)
    assert db.has_digest_for("2026-08-16") is True
    assert db.has_digest_for("2026-08-17") is False


def test_channel_binding_upsert_and_uniqueness(db: Database):
    db.upsert_channel_binding("telegram", "conv-1", "alice", NOW)
    db.upsert_channel_binding("telegram", "conv-1", "alice", NOW + timedelta(minutes=5))
    bindings = db.list_channel_bindings()
    assert len(bindings) == 1  # same (channel, conversation_id) -> updated, not duplicated
    assert bindings[0].last_active_at == NOW + timedelta(minutes=5)


def test_channel_binding_distinct_channels_and_conversations(db: Database):
    db.upsert_channel_binding("telegram", "conv-1", "alice", NOW)
    db.upsert_channel_binding("discord", "conv-9", "alice#0001", NOW)
    bindings = {(b.channel, b.conversation_id) for b in db.list_channel_bindings()}
    assert bindings == {("telegram", "conv-1"), ("discord", "conv-9")}
