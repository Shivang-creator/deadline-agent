#!/usr/bin/env python3
"""Run the interactive fake-channel REPL — no credentials needed.

Exercises the exact same core.handler.handle_message() that the real
Telegram/Discord adapters call. Try two fake channels in one session to see
cross-channel state sharing for yourself:

    uv run python scripts/run_fake.py
    > :channel telegram
    > /add OregonHacks tomorrow 11:59pm
    > :channel discord
    > /list                      <- shows the deadline added from "telegram"
    > :advance 23h 59m
    > :tick                      <- alerts fire, printed instead of sent

Usage:
    uv run python scripts/run_fake.py [db_path] [--real-clock]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deadline_agent.adapters.fake_channel import main

if __name__ == "__main__":
    main()
