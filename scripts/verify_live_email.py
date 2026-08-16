#!/usr/bin/env python3
"""One-off, manual live-verification script — NOT part of the pytest suite
(it needs network + a live Caspian gateway + leaves state on Caspian's
servers, none of which belong in an offline, deterministic test run).

Purpose: prove the REAL adapter wiring in adapters/caspian_app.py (the exact
`connect_*` + `register_handler` + core.handler.handle_message chain used
for Telegram/Discord) actually works against Caspian's live gateway — using
the one channel that needs zero external credentials: instant hosted email.
This is the one piece of the "real, not mocked" requirement we CAN verify
before Telegram/Discord tokens exist.

Usage:
    uv run python scripts/verify_live_email.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from caspian_sdk import CommClient

from deadline_agent.adapters.caspian_app import register_handler
from deadline_agent.config import load_env_local
from deadline_agent.core.clock import SystemClock
from deadline_agent.core.db import Database


def main() -> None:
    load_env_local()  # caspian_sdk only auto-reads ./.env, not ./.env.local
    db = Database(Path("/tmp/deadline_agent_live_email_verify.db"))
    clock = SystemClock()

    client = CommClient()  # reads CASPIAN_API_KEY / CASPIAN_BASE_URL from env (now loaded above)
    inbox = client.connect_email(username="deadline-agent-verify")
    print(f"Live email connected: {inbox['address']}")

    replies: list[str] = []

    # register_handler() is the exact function caspian_app.run() calls for
    # the real Telegram/Discord deployment — this is not a reimplementation.
    register_handler(client, db, clock, ai_fallback=None)

    # Wrap the SDK's reply so we can see what came back, in addition to the
    # real HTTP call it makes to the gateway.
    original_reply = client.reply

    def spy_reply(message_id, text=None, **kwargs):
        if text:
            replies.append(text)
            print(f"  bot replied: {text!r}")
        return original_reply(message_id, text=text, **kwargs)

    client.reply = spy_reply

    print("\nSending a real test email: '/add Live Verify Deadline in 2 days' ...")
    client.test_email(text="/add Live Verify Deadline in 2 days", subject="deadline-agent live check")

    # Poll dispatch_pending() a few times — this is exactly what listen()
    # does internally, just without blocking forever.
    seq = 0
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not replies:
        seq = client.dispatch_pending(after_seq=seq)
        time.sleep(1.0)

    if not replies:
        print("\nNo reply observed within 30s — see gateway logs / retry.")
        sys.exit(1)

    print("\nSending '/list' to confirm the deadline round-tripped through the real gateway...")
    client.test_email(text="/list", subject="deadline-agent live check 2")
    deadline = time.monotonic() + 30
    before = len(replies)
    while time.monotonic() < deadline and len(replies) == before:
        seq = client.dispatch_pending(after_seq=seq)
        time.sleep(1.0)

    print(f"\nAll replies observed: {replies}")
    assert any("Live Verify Deadline" in r for r in replies), "seeded deadline not visible in /list reply"
    print("\nLIVE VERIFIED: real Caspian gateway -> real on_message dispatch -> "
          "real core.handler.handle_message -> real message.reply(), round-tripped over HTTP.")
    db.close()


if __name__ == "__main__":
    main()
