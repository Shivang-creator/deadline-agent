"""Exercises the core handler exclusively through the fake-channel adapter's
dispatch() — the same path the interactive REPL and the architecture check
use. If this suite passes, the deterministic core works end to end without
any network, tokens, or Caspian import."""

from __future__ import annotations

from deadline_agent.adapters.fake_channel import dispatch
from deadline_agent.core.db import Database

from .conftest import REFERENCE_NOW


def send(db, clock, text, *, channel="telegram", conversation_id="conv-1", sender_id="alice"):
    return dispatch(
        db, clock, channel=channel, conversation_id=conversation_id,
        sender_id=sender_id, text=text,
    )


def test_help(db: Database, clock):
    reply = send(db, clock, "/help")
    assert "/add" in reply and "/list" in reply and "/remove" in reply


def test_add_then_list(db: Database, clock):
    reply = send(db, clock, "/add OregonHacks tomorrow 11:59pm")
    assert "Tracking" in reply and "OregonHacks" in reply

    listing = send(db, clock, "/list")
    assert "OregonHacks" in listing
    assert "OVERDUE" not in listing


def test_list_when_empty(db: Database, clock):
    reply = send(db, clock, "/list")
    assert "Nothing tracked" in reply


def test_add_unparseable_date_gives_helpful_error(db: Database, clock):
    reply = send(db, clock, "/add MyThing whenever I feel like it")
    assert "couldn't find a date" in reply.lower() or "date/time" in reply.lower()
    # must not have been persisted
    assert send(db, clock, "/list") == "Nothing tracked yet. Add one: /add <name> <date/time>"


def test_add_past_date_is_rejected(db: Database, clock):
    reply = send(db, clock, "/add OldThing 2020-01-01T00:00:00Z")
    assert "already in the past" in reply
    assert "Nothing tracked" in send(db, clock, "/list")


def test_remove_exact_match(db: Database, clock):
    send(db, clock, "/add OregonHacks tomorrow 11:59pm")
    reply = send(db, clock, "/remove OregonHacks")
    assert "Removed" in reply and "OregonHacks" in reply
    assert "Nothing tracked" in send(db, clock, "/list")


def test_remove_case_insensitive(db: Database, clock):
    send(db, clock, "/add OregonHacks tomorrow 11:59pm")
    reply = send(db, clock, "/remove oregonhacks")
    assert "Removed" in reply


def test_remove_partial_unique_match(db: Database, clock):
    send(db, clock, "/add OregonHacks tomorrow 11:59pm")
    reply = send(db, clock, "/remove Oregon")
    assert "Removed" in reply and "OregonHacks" in reply


def test_remove_ambiguous_partial_match(db: Database, clock):
    send(db, clock, "/add CS Girlies tomorrow 9pm")
    send(db, clock, "/add CS Society tomorrow 9pm")
    reply = send(db, clock, "/remove CS")
    assert "Multiple matches" in reply
    # neither should have been removed
    listing = send(db, clock, "/list")
    assert "CS Girlies" in listing and "CS Society" in listing


def test_remove_not_found(db: Database, clock):
    reply = send(db, clock, "/remove NoSuchThing")
    assert "No tracked deadline matches" in reply


def test_remove_missing_name(db: Database, clock):
    reply = send(db, clock, "/remove")
    assert "Usage: /remove" in reply


def test_unknown_command_without_ai_fallback(db: Database, clock):
    reply = send(db, clock, "yo what's due soon")
    assert "/help" in reply


def test_unknown_command_with_ai_fallback_rewrites_to_list(db: Database, clock):
    from deadline_agent.adapters.fake_channel import dispatch as _dispatch

    def fake_fallback(raw_text: str) -> str | None:
        assert raw_text == "what's due soon?"
        return "/list"

    reply = _dispatch(
        db, clock, channel="telegram", conversation_id="c1", sender_id="a",
        text="what's due soon?", ai_fallback=fake_fallback,
    )
    assert "Nothing tracked" in reply  # /list on an empty db


def test_ai_fallback_returning_none_falls_back_to_help_hint(db: Database, clock):
    reply = dispatch(
        db, clock, channel="telegram", conversation_id="c1", sender_id="a",
        text="asdkjfh", ai_fallback=lambda _text: None,
    )
    assert "/help" in reply


def test_list_shows_overdue(db: Database, clock):
    send(db, clock, "/add PastDue in 1 hour")
    clock.advance(hours=2)
    listing = send(db, clock, "/list")
    assert "OVERDUE" in listing


def test_every_inbound_message_creates_a_channel_binding(db: Database, clock):
    send(db, clock, "/help", channel="discord", conversation_id="ch-42", sender_id="bob")
    bindings = db.list_channel_bindings()
    assert any(b.channel == "discord" and b.conversation_id == "ch-42" for b in bindings)


def test_reference_now_fixture_is_in_the_future_relative_to_seed_data():
    # Sanity check the fixture itself sits before the 17/18 Aug seed dates.
    assert REFERENCE_NOW.year == 2026 and REFERENCE_NOW.month == 8 and REFERENCE_NOW.day == 16
