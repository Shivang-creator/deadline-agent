from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from deadline_agent.core.clock import FakeClock
from deadline_agent.core.db import Database

# Fixed reference "now" for deterministic tests: Sunday 16 Aug 2026, 12:00 UTC
# (17:30 IST). Chosen to sit comfortably before the seeded 17/18 Aug deadlines.
REFERENCE_NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(REFERENCE_NOW)


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    yield database
    database.close()
