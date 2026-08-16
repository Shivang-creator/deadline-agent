"""THE core handler. This is the one function every channel adapter calls.

handle_message() is the single place command parsing, deadline CRUD, and
cross-channel bookkeeping happen. It knows nothing about Telegram, Discord,
Caspian, HTTP, or any transport — it takes a plain InboundMessage and a
Database/Clock, and returns a plain HandlerResult. Both the real Caspian
adapter (adapters/caspian_app.py) and the local fake-channel harness
(adapters/fake_channel.py) call this exact function; neither re-implements
any of this logic. That is what "one handler, N channels" means here, and
it's mechanically checked in tests/test_architecture.py (no import of
caspian_sdk or any channel-specific name anywhere under core/).
"""

from __future__ import annotations

from collections.abc import Callable

from .clock import Clock
from .commands import (
    AddCommand,
    Command,
    HelpCommand,
    ListCommand,
    RemoveCommand,
    UnknownCommand,
    parse_command,
)
from .db import Database
from .formatting import format_dt, format_timedelta
from .models import HandlerResult, InboundMessage

HELP_TEXT = """Deadline — I track your hackathon/project deadlines and ping you before you miss them.

Commands (work the same on every connected channel):
  /add <name> <date/time>   Track a new deadline. Dates are forgiving:
                             "17 Aug 9pm", "tomorrow 3am", "in 6 hours",
                             or a plain ISO timestamp all work.
  /list                     Everything tracked, soonest first.
  /remove <name>            Stop tracking something (exact or partial match).
  /help                     This message.

I alert automatically at 24h, 6h, and 1h before each deadline, plus a daily
digest of everything still open — sent to whichever channel(s) you've used."""

# An optional hook: given raw text that didn't match any known command, try
# to rewrite it into one that does (e.g. via an LLM). Returns a command
# string to re-parse, or None to give up and show the help hint. Injected so
# core/ never hard-depends on any particular AI backend or network call —
# see adapters/../core/ai_fallback.py for the real (Featherless-backed) one.
AiFallback = Callable[[str], "str | None"]


def handle_message(
    db: Database,
    clock: Clock,
    message: InboundMessage,
    ai_fallback: AiFallback | None = None,
) -> HandlerResult:
    now = clock.now()

    # Every inbound message — regardless of command — marks this channel／
    # conversation as one the user is active on. This is the entire
    # mechanism behind cross-channel state and "alert wherever they're near".
    db.upsert_channel_binding(
        message.channel, message.conversation_id, message.sender_id, now
    )

    command = parse_command(message.text, now=now)

    if isinstance(command, UnknownCommand) and ai_fallback is not None and command.raw:
        rewritten = ai_fallback(command.raw)
        if rewritten:
            reparsed = parse_command(rewritten, now=now)
            if not isinstance(reparsed, UnknownCommand):
                command = reparsed

    return _dispatch(db, now, message, command)


def _dispatch(db: Database, now, message: InboundMessage, command: Command) -> HandlerResult:
    if isinstance(command, AddCommand):
        return _handle_add(db, now, message, command)
    if isinstance(command, ListCommand):
        return _handle_list(db, now)
    if isinstance(command, RemoveCommand):
        return _handle_remove(db, now, command)
    if isinstance(command, HelpCommand):
        return HandlerResult(reply_text=HELP_TEXT)
    return _handle_unknown()


def _handle_add(db: Database, now, message: InboundMessage, command: AddCommand) -> HandlerResult:
    if not command.name and not command.raw_when:
        return HandlerResult(
            reply_text="Usage: /add <name> <date/time>\n"
            'Example: /add Submit project tomorrow 9pm'
        )
    if command.due_at is None:
        near = f' in "{command.raw_when}"' if command.raw_when else ""
        return HandlerResult(
            reply_text=f"Couldn't find a date/time{near}. Try: /add <name> <when>, "
            'e.g. /add Submit project tomorrow 9pm, or /add OregonHacks 18 Aug 11:59pm'
        )
    if command.due_at <= now:
        return HandlerResult(
            reply_text=f'"{command.name}" parsed to {format_dt(command.due_at)}, which is '
            "already in the past — not tracking it. If that's wrong, be more specific "
            "(include the year, or use an ISO timestamp)."
        )
    deadline = db.add_deadline(
        name=command.name, due_at=command.due_at, created_at=now, source_channel=message.channel
    )
    remaining = format_timedelta(deadline.due_at - now)
    return HandlerResult(
        reply_text=f'Tracking "{deadline.name}" — due {format_dt(deadline.due_at)} '
        f"({remaining} from now). I'll alert at 24h, 6h, and 1h before, wherever you're active."
    )


def _handle_list(db: Database, now) -> HandlerResult:
    deadlines = db.list_deadlines()
    if not deadlines:
        return HandlerResult(reply_text="Nothing tracked yet. Add one: /add <name> <date/time>")
    lines = ["Tracked deadlines (soonest first):"]
    for d in deadlines:
        if d.due_at <= now:
            status = f"OVERDUE by {format_timedelta(now - d.due_at)}"
        else:
            status = f"in {format_timedelta(d.due_at - now)}"
        lines.append(f"- {d.name} — {format_dt(d.due_at)} ({status})")
    return HandlerResult(reply_text="\n".join(lines))


def _handle_remove(db: Database, now, command: RemoveCommand) -> HandlerResult:
    if not command.name:
        return HandlerResult(reply_text="Usage: /remove <name>")
    deadlines = db.list_deadlines()
    needle = command.name.strip().lower()

    exact = [d for d in deadlines if d.name.lower() == needle]
    if exact:
        db.remove_deadline(exact[0].id, now)
        return HandlerResult(reply_text=f'Removed "{exact[0].name}".')

    partial = [d for d in deadlines if needle in d.name.lower()]
    if len(partial) == 1:
        db.remove_deadline(partial[0].id, now)
        return HandlerResult(reply_text=f'Removed "{partial[0].name}".')
    if len(partial) > 1:
        names = ", ".join(f'"{d.name}"' for d in partial)
        return HandlerResult(reply_text=f"Multiple matches: {names}. Be more specific.")

    return HandlerResult(reply_text=f'No tracked deadline matches "{command.name}".')


def _handle_unknown() -> HandlerResult:
    return HandlerResult(
        reply_text='Not sure what you mean. Send /help for commands, e.g. '
        '/add OregonHacks 18 Aug 11:59pm'
    )
