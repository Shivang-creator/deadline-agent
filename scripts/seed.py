#!/usr/bin/env python3
"""Seed the SQLite state with real, currently-open hackathon deadlines, so
the demo's /list shows genuine data instead of placeholder examples.

Idempotent: re-running skips any name that's already tracked (case-
insensitive match), so it's safe to run again after the live tokens land.

Usage:
    uv run python scripts/seed.py [db_path]
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deadline_agent.config import DEFAULT_DB_PATH
from deadline_agent.core.clock import SystemClock
from deadline_agent.core.db import Database

IST = ZoneInfo("Asia/Kolkata")

# Real, currently-open deadlines as of 16 Aug 2026 (approximate times — this
# is about making the demo authentic, not submission-critical precision).
SEED_DEADLINES: list[tuple[str, datetime]] = [
    ("CS Girlies", datetime(2026, 8, 17, 23, 59, tzinfo=IST)),
    ("Social Media Automation", datetime(2026, 8, 17, 20, 0, tzinfo=IST)),
    ("Impact Forge", datetime(2026, 8, 17, 23, 59, tzinfo=IST)),
    ("YouCam API", datetime(2026, 8, 17, 18, 0, tzinfo=IST)),
    ("OregonHacks", datetime(2026, 8, 18, 23, 59, tzinfo=IST)),
]


def seed(db_path: str) -> None:
    db = Database(Path(db_path))
    clock = SystemClock()
    now = clock.now()
    existing = {d.name.lower() for d in db.list_deadlines()}

    added = 0
    for name, due_at_local in SEED_DEADLINES:
        if name.lower() in existing:
            print(f"skip (already tracked): {name}")
            continue
        deadline = db.add_deadline(
            name=name, due_at=due_at_local, created_at=now, source_channel="seed"
        )
        print(f"seeded: {deadline.name} -> due {deadline.due_at.isoformat()}")
        added += 1
    db.close()
    print(f"\nDone. {added} new deadline(s) seeded into {db_path}.")
    print(
        "Note: these have no channel binding yet, so no alerts fire for them until "
        "someone messages the bot at least once (on any channel) — that's what "
        "creates the binding the scheduler sends alerts to."
    )


if __name__ == "__main__":
    seed(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH)
