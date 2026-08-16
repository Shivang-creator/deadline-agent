"""Proves state is genuinely shared across channels through one handler
instance — the core requirement behind "duplicating your handler per
channel doesn't count". Two fake channels, one Database, one handler."""

from __future__ import annotations

from deadline_agent.adapters.fake_channel import dispatch
from deadline_agent.core.db import Database
from deadline_agent.core.scheduler import tick


def test_added_on_telegram_visible_on_discord(db: Database, clock):
    dispatch(
        db, clock, channel="telegram", conversation_id="tg-1", sender_id="alice",
        text="/add OregonHacks tomorrow 11:59pm",
    )
    listing = dispatch(
        db, clock, channel="discord", conversation_id="dc-1", sender_id="alice#0001",
        text="/list",
    )
    assert "OregonHacks" in listing


def test_removed_on_discord_gone_on_telegram(db: Database, clock):
    dispatch(db, clock, channel="telegram", conversation_id="tg-1", sender_id="alice",
             text="/add ImpactForge tomorrow 9pm")
    dispatch(db, clock, channel="discord", conversation_id="dc-1", sender_id="alice#0001",
             text="/remove ImpactForge")
    listing = dispatch(db, clock, channel="telegram", conversation_id="tg-1", sender_id="alice",
                        text="/list")
    assert "ImpactForge" not in listing


def test_scheduler_alerts_reach_both_channels_once_both_have_spoken(db: Database, clock):
    # Establish both bindings first (both channels have "been active").
    dispatch(db, clock, channel="telegram", conversation_id="tg-1", sender_id="alice",
             text="/help")
    dispatch(db, clock, channel="discord", conversation_id="dc-1", sender_id="alice#0001",
             text="/help")
    dispatch(db, clock, channel="telegram", conversation_id="tg-1", sender_id="alice",
             text="/add RushJob in 45 minutes")

    fired = tick(db, clock)
    destinations = {(n.channel, n.conversation_id) for n in fired}
    assert ("telegram", "tg-1") in destinations
    assert ("discord", "dc-1") in destinations


def test_interleaved_messages_across_channels_share_one_deadline_list(db: Database, clock):
    dispatch(db, clock, channel="telegram", conversation_id="tg-1", sender_id="a", text="/add A tomorrow 1pm")
    dispatch(db, clock, channel="discord", conversation_id="dc-1", sender_id="b", text="/add B tomorrow 2pm")
    dispatch(db, clock, channel="telegram", conversation_id="tg-1", sender_id="a", text="/add C tomorrow 3pm")

    listing_from_discord = dispatch(db, clock, channel="discord", conversation_id="dc-1",
                                     sender_id="b", text="/list")
    for name in ("A", "B", "C"):
        assert name in listing_from_discord
