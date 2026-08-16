#!/usr/bin/env python3
"""Phase 2 entry point — starts the real, live agent on Telegram and/or
Discord through caspian-sdk. Only works once .env.local has a real
CASPIAN_API_KEY and at least one of TELEGRAM_BOT_TOKEN / DISCORD_BOT_TOKEN.

Usage:
    uv run python scripts/run_live.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deadline_agent.adapters.caspian_app import run

if __name__ == "__main__":
    run()
