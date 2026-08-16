"""SQLite persistence: tracked deadlines, per-threshold "already notified"
state, the daily-digest log, and cross-channel bindings.

This is the only place that talks to disk. Everything else in core/ works
with the dataclasses in models.py. Thread-safe (a single connection guarded
by a lock) because the scheduler tick runs on a background thread while
message handling runs on whatever thread the channel adapter dispatches on.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from .models import ChannelBinding, Deadline

_SCHEMA = """
CREATE TABLE IF NOT EXISTS deadlines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    due_at          TEXT NOT NULL,      -- ISO 8601 UTC
    created_at      TEXT NOT NULL,      -- ISO 8601 UTC
    source_channel  TEXT NOT NULL,
    removed_at      TEXT                -- ISO 8601 UTC, NULL while active
);

CREATE TABLE IF NOT EXISTS notified_thresholds (
    deadline_id TEXT NOT NULL,
    kind        TEXT NOT NULL,          -- "alert:24h" | "alert:6h" | "alert:1h"
    sent_at     TEXT NOT NULL,
    PRIMARY KEY (deadline_id, kind)
);

CREATE TABLE IF NOT EXISTS digest_log (
    digest_date TEXT PRIMARY KEY,       -- YYYY-MM-DD in the configured digest timezone
    sent_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channel_bindings (
    channel         TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    sender_id       TEXT,
    last_active_at  TEXT NOT NULL,
    PRIMARY KEY (channel, conversation_id)
);
"""


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _parse(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class Database:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- deadlines ------------------------------------------------------

    def add_deadline(
        self, name: str, due_at: datetime, created_at: datetime, source_channel: str
    ) -> Deadline:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO deadlines (name, due_at, created_at, source_channel) "
                "VALUES (?, ?, ?, ?)",
                (name, _iso(due_at), _iso(created_at), source_channel),
            )
            self._conn.commit()
            row_id = cur.lastrowid
        return Deadline(
            id=row_id, name=name, due_at=due_at, created_at=created_at,
            source_channel=source_channel,
        )

    def list_deadlines(self, include_removed: bool = False) -> list[Deadline]:
        query = "SELECT * FROM deadlines"
        if not include_removed:
            query += " WHERE removed_at IS NULL"
        query += " ORDER BY due_at ASC"
        with self._lock:
            rows = self._conn.execute(query).fetchall()
        return [self._row_to_deadline(r) for r in rows]

    def get_deadline(self, deadline_id: int) -> Deadline | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM deadlines WHERE id = ?", (deadline_id,)
            ).fetchone()
        return self._row_to_deadline(row) if row else None

    def remove_deadline(self, deadline_id: int, removed_at: datetime) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE deadlines SET removed_at = ? WHERE id = ?",
                (_iso(removed_at), deadline_id),
            )
            self._conn.commit()

    @staticmethod
    def _row_to_deadline(row: sqlite3.Row) -> Deadline:
        return Deadline(
            id=row["id"],
            name=row["name"],
            due_at=_parse(row["due_at"]),
            created_at=_parse(row["created_at"]),
            source_channel=row["source_channel"],
        )

    # -- notification thresholds ("already notified", restart-safe) ----

    def has_notified(self, deadline_id: int, kind: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM notified_thresholds WHERE deadline_id = ? AND kind = ?",
                (str(deadline_id), kind),
            ).fetchone()
        return row is not None

    def mark_notified(self, deadline_id: int, kind: str, sent_at: datetime) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO notified_thresholds (deadline_id, kind, sent_at) "
                "VALUES (?, ?, ?)",
                (str(deadline_id), kind, _iso(sent_at)),
            )
            self._conn.commit()

    # -- daily digest log -------------------------------------------------

    def has_digest_for(self, digest_date: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM digest_log WHERE digest_date = ?", (digest_date,)
            ).fetchone()
        return row is not None

    def mark_digest_sent(self, digest_date: str, sent_at: datetime) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO digest_log (digest_date, sent_at) VALUES (?, ?)",
                (digest_date, _iso(sent_at)),
            )
            self._conn.commit()

    # -- cross-channel bindings ------------------------------------------
    # Every (channel, conversation_id) that has ever messaged the agent.
    # This is what makes "sent to whichever channel(s) the user has been
    # active on" possible, and what proves state is shared across channels:
    # a binding created by a Telegram message is visible to a /list on
    # Discord because both channels dispatch into this same table.

    def upsert_channel_binding(
        self, channel: str, conversation_id: str, sender_id: str | None, now: datetime
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO channel_bindings (channel, conversation_id, sender_id, last_active_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(channel, conversation_id) DO UPDATE SET "
                "sender_id = excluded.sender_id, last_active_at = excluded.last_active_at",
                (channel, conversation_id, sender_id, _iso(now)),
            )
            self._conn.commit()

    def list_channel_bindings(self) -> list[ChannelBinding]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM channel_bindings ORDER BY last_active_at DESC"
            ).fetchall()
        return [
            ChannelBinding(
                channel=r["channel"],
                conversation_id=r["conversation_id"],
                sender_id=r["sender_id"],
                last_active_at=_parse(r["last_active_at"]),
            )
            for r in rows
        ]
