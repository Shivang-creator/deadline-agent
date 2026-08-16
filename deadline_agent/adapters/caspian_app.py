"""Real channel wiring: Telegram + Discord, through caspian-sdk, through ONE
handler.

This file is the entire adapter layer for real channels, and it is thin on
purpose — that's the point of the SDK's "duplicating your handler per
channel doesn't count" rule. It does exactly three things:

  1. `connect_telegram(bot_token=...)` and `connect_discord(bot_token=...)`
     on a single `CommClient` — see caspian-sdk's `one_handler_three_channels.py`
     example, which this mirrors.
  2. Register exactly ONE `@client.on_message` handler. It builds an
     InboundMessage from Caspian's already-normalized `message` object and
     calls the *same* `core.handler.handle_message()` that the fake-channel
     adapter and every offline test call — no logic is duplicated here.
  3. Run a background scheduler loop that calls `core.scheduler.run_all()`
     on an interval and delivers any resulting Notification via
     `client.send_message(conversation_id, text=...)` (agent-initiated send,
     same pattern as caspian-sdk's `telegram_reminders.py` example).

Nothing about deadlines, date parsing, command parsing, or scheduling logic
lives in this file. If you're looking for that, it's all in
deadline_agent/core/, and it's fully covered by tests that never import this
module or caspian_sdk at all.

Cannot be exercised live without real credentials: CASPIAN_API_KEY (mint a
free one — `caspian init`, or `POST {gateway}/v1/projects/sandbox`, no
sign-in needed for free channels) and at least one of TELEGRAM_BOT_TOKEN /
DISCORD_BOT_TOKEN. See README.md "Setup" and .env.local.example. This module
is written and import-clean today, but NOT live-verified until those exist —
see the README's "Honest limits" section for exactly what that means.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from caspian_sdk import CommClient

from ..config import DEFAULT_DB_PATH, DEFAULT_TICK_SECONDS, load_env_local
from ..core.ai_fallback import build_featherless_fallback
from ..core.clock import Clock, SystemClock
from ..core.db import Database
from ..core.handler import AiFallback, handle_message
from ..core.models import InboundMessage, Notification
from ..core.scheduler import run_all

logger = logging.getLogger("deadline_agent.caspian_app")


def build_ai_fallback() -> AiFallback | None:
    """Wires the optional Featherless fallback from env — absent entirely if
    FEATHERLESS_API_KEY isn't set, exactly like handler.handle_message()'s
    default. Not required for the product to work."""
    api_key = os.environ.get("FEATHERLESS_API_KEY")
    if not api_key:
        return None
    return build_featherless_fallback(
        api_key=api_key,
        base_url=os.environ.get("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
        model=os.environ.get("FEATHERLESS_MODEL", "deepseek-ai/DeepSeek-V3-0324"),
    )


def connect_channels(client: CommClient) -> list[str]:
    """Connect whichever of Telegram/Discord have a token configured.

    At least one must be present. Both is the normal end state ("at least
    two supported channels through one handler"); running with just one
    while waiting on the other token is intentionally supported, since
    tokens are arriving at different times in this project's timeline.
    """
    connected: list[str] = []
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    discord_token = os.environ.get("DISCORD_BOT_TOKEN")

    if telegram_token:
        client.connect_telegram(bot_token=telegram_token)
        connected.append("telegram")
        logger.info("Connected Telegram.")
    if discord_token:
        # Discord bot application must have the "MESSAGE CONTENT" privileged
        # intent enabled (discord.com/developers -> your app -> Bot ->
        # Privileged Gateway Intents), or inbound message text arrives empty.
        # See README.md "Setup -> Discord" for the exact steps.
        client.connect_discord(bot_token=discord_token)
        connected.append("discord")
        logger.info("Connected Discord.")

    if not connected:
        raise RuntimeError(
            "No channel tokens configured. Set TELEGRAM_BOT_TOKEN and/or "
            "DISCORD_BOT_TOKEN in .env.local before running the live app."
        )
    return connected


def register_handler(
    client: CommClient, db: Database, clock: Clock, ai_fallback: AiFallback | None
) -> None:
    """The ONE handler. Every connected channel dispatches inbound messages
    here — this function is registered exactly once, regardless of how many
    connect_*() calls preceded it."""

    @client.on_message
    def on_message(message):
        inbound = InboundMessage(
            channel=message.channel,
            conversation_id=message.conversation_id,
            sender_id=(message.sender or {}).get("address") if message.sender else None,
            text=message.text or "",
        )
        # Logged so a live run leaves an auditable transcript of exactly what
        # arrived on which channel and exactly what went back — the evidence
        # trail for "this really ran on real channels", not a mock.
        logger.info(
            "INBOUND  [%s] conv=%s from=%s text=%r",
            inbound.channel, inbound.conversation_id, inbound.sender_id, inbound.text,
        )
        result = handle_message(db, clock, inbound, ai_fallback=ai_fallback)
        message.reply(result.reply_text)
        logger.info(
            "REPLY    [%s] conv=%s text=%r",
            inbound.channel, inbound.conversation_id, result.reply_text,
        )


def _deliver(client: CommClient, notification: Notification) -> None:
    try:
        client.send_message(notification.conversation_id, text=notification.text)
        logger.info(
            "PROACTIVE[%s] conv=%s kind=%s deadline=%s text=%r",
            notification.channel, notification.conversation_id, notification.kind,
            notification.deadline_id, notification.text,
        )
    except Exception:
        logger.exception(
            "Failed to deliver %s notification (deadline %s) to %s:%s",
            notification.kind, notification.deadline_id,
            notification.channel, notification.conversation_id,
        )


def _scheduler_loop(
    client: CommClient, db: Database, clock: Clock, stop: threading.Event, interval: float
) -> None:
    while not stop.is_set():
        try:
            for notification in run_all(db, clock):
                _deliver(client, notification)
        except Exception:
            logger.exception("Scheduler tick failed; will retry next interval")
        stop.wait(interval)


def run(db_path: str | Path = DEFAULT_DB_PATH, *, tick_seconds: float = DEFAULT_TICK_SECONDS) -> None:
    """Start the real, live agent: connect channels, register the one
    handler, start the scheduler loop, then block on client.listen() until
    Ctrl+C. This is the Phase 2 entry point — see scripts/run_live.py."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    # The SDK polls the gateway ~once a second; at INFO that buries the
    # INBOUND/REPLY/PROACTIVE lines that are the actual transcript.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_env_local()  # caspian_sdk only auto-reads ./.env, not ./.env.local
    # A shorter tick makes a near-future test alert land promptly during a
    # live demo; the default 60s is the sane production value.
    tick_seconds = float(os.environ.get("DEADLINE_TICK_SECONDS", tick_seconds))
    db = Database(Path(db_path))
    clock = SystemClock()
    ai_fallback = build_ai_fallback()

    client = CommClient()  # reads CASPIAN_API_KEY / CASPIAN_BASE_URL from env (now loaded above)
    connected = connect_channels(client)
    print(f"Deadline is live on: {', '.join(connected)}")

    register_handler(client, db, clock, ai_fallback)

    stop = threading.Event()
    thread = threading.Thread(
        target=_scheduler_loop, args=(client, db, clock, stop, tick_seconds), daemon=True,
    )
    thread.start()

    try:
        client.listen()
    finally:
        stop.set()
        db.close()


if __name__ == "__main__":
    run()
