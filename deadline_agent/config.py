"""The handful of shared defaults used by more than one entry point (the
live Caspian app, the seed script). Not "core" logic — just paths/knobs."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DB_PATH = "deadline_agent.db"
DEFAULT_TICK_SECONDS = 60.0


def load_env_local(path: str | Path = ".env.local") -> None:
    """Load KEY=VALUE lines from .env.local into os.environ, without
    overwriting a variable that's already set in the real environment.

    caspian_sdk's own CommClient auto-reads only ./.env — not .env.local —
    so every real (non-test) entry point in this project calls this first,
    to honor the .env.local convention this project was asked to use.
    """
    file_path = Path(path)
    if not file_path.exists():
        return
    for line in file_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key, value)
