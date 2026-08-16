"""The local test/dev channel adapter — no network, no tokens, no Caspian.

This is what Phase 1 validates the entire product against before any real
Telegram/Discord token exists. `dispatch()` is the thin adapter function:
it takes a (channel, conversation_id, sender, text) tuple — exactly the
shape a real inbound message reduces to — builds an InboundMessage, and
calls the *exact same* core.handler.handle_message() that the real Caspian
adapter calls. Nothing about command parsing, persistence, or scheduling is
reimplemented here.

Two ways to use it:
  1. Programmatically, from tests (see tests/) — call dispatch() directly
     against a Database + FakeClock, in-process, fully deterministic.
  2. Interactively, as a terminal REPL (`python -m deadline_agent.adapters.fake_channel`)
     that simulates two fake "channels" against one shared handler + DB, lets
     you fast-forward a fake clock, and prints any alerts that would fire —
     a full manual walkthrough of the product with zero credentials.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from ..core.clock import Clock, FakeClock, SystemClock
from ..core.db import Database
from ..core.handler import AiFallback, handle_message
from ..core.models import InboundMessage, Notification
from ..core.scheduler import run_all

DEFAULT_FAKE_DB = "deadline_agent_fake.db"


def dispatch(
    db: Database,
    clock: Clock,
    *,
    channel: str,
    conversation_id: str,
    sender_id: str | None,
    text: str,
    ai_fallback: AiFallback | None = None,
) -> str:
    """The fake channel's entire adapter surface: build InboundMessage, call
    the one core handler, return the reply text. Mirrors exactly what
    adapters/caspian_app.py does with a real Caspian `message` object."""
    message = InboundMessage(
        channel=channel, conversation_id=conversation_id, sender_id=sender_id, text=text
    )
    result = handle_message(db, clock, message, ai_fallback=ai_fallback)
    return result.reply_text


_DURATION_RE = re.compile(r"(\d+)\s*(d|h|m)", re.IGNORECASE)


def parse_duration(text: str) -> dict[str, int]:
    """"6h", "90m", "2d 3h", "1h30m" -> kwargs for FakeClock.advance()."""
    kwargs: dict[str, int] = {}
    unit_map = {"d": "days", "h": "hours", "m": "minutes"}
    for amount, unit in _DURATION_RE.findall(text):
        key = unit_map[unit.lower()]
        kwargs[key] = kwargs.get(key, 0) + int(amount)
    return kwargs


_HELP = """Fake-channel REPL — simulates real inbound messages against the one core handler.

Meta-commands (start with ':'):
  :channel <name>     switch the active fake channel (e.g. telegram, discord)
  :conv <id>          switch the active conversation id on this channel
  :as <sender>        set the sender label for subsequent messages
  :advance <dur>      fast-forward the fake clock, e.g. :advance 6h, :advance 2d 3h
  :tick               run the scheduler now; prints any notifications that would fire
  :now                print the current fake clock time
  :help               this message
  :quit               exit

Anything else is sent as a message on the active channel/conversation — try
/add, /list, /remove, /help exactly like a real user would.
"""


def _print_notifications(notifications: list[Notification]) -> None:
    if not notifications:
        print("(scheduler ran: no notifications due)")
        return
    for n in notifications:
        print(f"  [would send -> {n.channel}:{n.conversation_id}] ({n.kind}) {n.text}")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    db_path = argv[0] if argv else DEFAULT_FAKE_DB
    use_real_clock = "--real-clock" in argv

    db = Database(Path(db_path))
    clock: Clock = SystemClock() if use_real_clock else FakeClock()

    import os

    from ..config import load_env_local

    load_env_local()  # picks up FEATHERLESS_* from .env.local if present

    ai_fallback: AiFallback | None = None
    if os.environ.get("FEATHERLESS_API_KEY"):
        from ..core.ai_fallback import build_featherless_fallback

        ai_fallback = build_featherless_fallback(
            api_key=os.environ["FEATHERLESS_API_KEY"],
            base_url=os.environ.get("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
            model=os.environ.get("FEATHERLESS_MODEL", "deepseek-ai/DeepSeek-V3-0324"),
        )
        print("(AI fallback enabled via FEATHERLESS_API_KEY)")

    channel, conversation_id, sender = "telegram", "fake-conv-1", "you"
    print(f"Deadline — fake channel REPL. DB: {db_path}")
    print(f"Active: channel={channel} conversation={conversation_id} sender={sender}")
    print("Type :help for meta-commands, /help for the bot's own help.\n")

    try:
        for raw_line in sys.stdin:
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue
            if line.startswith(":"):
                parts = line[1:].split(maxsplit=1)
                cmd = parts[0].lower() if parts else ""
                arg = parts[1] if len(parts) > 1 else ""
                if cmd == "quit" or cmd == "exit":
                    break
                if cmd == "help":
                    print(_HELP)
                elif cmd == "channel" and arg:
                    channel = arg.strip()
                    print(f"-> active channel: {channel}")
                elif cmd == "conv" and arg:
                    conversation_id = arg.strip()
                    print(f"-> active conversation: {conversation_id}")
                elif cmd == "as" and arg:
                    sender = arg.strip()
                    print(f"-> active sender: {sender}")
                elif cmd == "now":
                    print(f"-> now: {clock.now().isoformat()}")
                elif cmd == "advance":
                    if isinstance(clock, FakeClock):
                        kwargs = parse_duration(arg)
                        if not kwargs:
                            print("Usage: :advance 6h   (or 2d, 90m, 2d 3h, ...)")
                        else:
                            new_now = clock.advance(**kwargs)
                            print(f"-> now: {new_now.isoformat()}")
                    else:
                        print("(--real-clock mode: cannot advance a real clock)")
                elif cmd == "tick":
                    notifications = run_all(db, clock)
                    _print_notifications(notifications)
                else:
                    print(f"Unknown meta-command: {line!r}. Try :help")
                continue

            reply = dispatch(
                db, clock, channel=channel, conversation_id=conversation_id,
                sender_id=sender, text=line, ai_fallback=ai_fallback,
            )
            print(f"[{channel}:{conversation_id}] {sender}> {line}")
            print(f"[{channel}:{conversation_id}] bot> {reply}\n")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        db.close()


if __name__ == "__main__":
    main()
