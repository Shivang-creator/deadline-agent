"""Parse raw inbound text into a structured Command. No I/O, no channel code.

The tricky part is `/add <name> <date/time>`: the boundary between the name
and the date phrase isn't marked. We resolve it by trying the LONGEST
possible date phrase first (i.e. the shortest name) and shrinking the date
phrase from the left, one token at a time, until something parses:

    "/add CS Girlies 17 Aug 9pm"
      i=1: name="CS"          when="Girlies 17 Aug 9pm"  -> doesn't parse
      i=2: name="CS Girlies"  when="17 Aug 9pm"           -> parses -> stop

    "/add Homework in 6 hours"
      i=1: name="Homework"    when="in 6 hours"           -> parses -> stop

This greedy "first suffix (from the left) that parses wins" rule handles
both "junk before the date" and "the date phrase is short" without any
required delimiter — but a delimiter still works fine, since by the time the
loop reaches it the remaining tokens parse straightforwardly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .parser import DEFAULT_TIMEZONE, parse_datetime


@dataclass(frozen=True)
class AddCommand:
    name: str
    due_at: datetime | None  # None => couldn't find a parseable date phrase
    raw_when: str  # the text we tried to parse as a date, for error messages


@dataclass(frozen=True)
class ListCommand:
    pass


@dataclass(frozen=True)
class RemoveCommand:
    name: str  # may be empty -> handler asks for one


@dataclass(frozen=True)
class HelpCommand:
    pass


@dataclass(frozen=True)
class UnknownCommand:
    raw: str


Command = AddCommand | ListCommand | RemoveCommand | HelpCommand | UnknownCommand

_ALIASES = {
    "/add": "/add",
    "/track": "/add",
    "/list": "/list",
    "/ls": "/list",
    "/remove": "/remove",
    "/rm": "/remove",
    "/delete": "/remove",
    "/del": "/remove",
    "/help": "/help",
    "/start": "/help",
}


def parse_command(
    text: str, *, now: datetime, timezone_name: str = DEFAULT_TIMEZONE
) -> Command:
    stripped = (text or "").strip()
    if not stripped or not stripped.startswith("/"):
        return UnknownCommand(raw=stripped)

    parts = stripped.split(maxsplit=1)
    verb = parts[0].lower()
    if "@" in verb:  # Telegram group chats allow "/add@YourBot ..."
        verb = verb.split("@", 1)[0]
    rest = parts[1] if len(parts) > 1 else ""

    canonical = _ALIASES.get(verb)
    if canonical == "/add":
        return _parse_add(rest, now=now, timezone_name=timezone_name)
    if canonical == "/list":
        return ListCommand()
    if canonical == "/remove":
        return RemoveCommand(name=rest.strip())
    if canonical == "/help":
        return HelpCommand()
    return UnknownCommand(raw=stripped)


def _parse_add(rest: str, *, now: datetime, timezone_name: str) -> AddCommand:
    rest = rest.strip()
    if not rest:
        return AddCommand(name="", due_at=None, raw_when="")

    tokens = rest.split()
    if len(tokens) < 2:
        return AddCommand(name=rest, due_at=None, raw_when="")

    for i in range(1, len(tokens)):
        candidate_when = " ".join(tokens[i:])
        due_at = parse_datetime(candidate_when, now=now, timezone_name=timezone_name)
        if due_at is not None:
            name = " ".join(tokens[:i])
            return AddCommand(name=name, due_at=due_at, raw_when=candidate_when)

    return AddCommand(name=rest, due_at=None, raw_when=rest)
