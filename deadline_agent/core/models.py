"""Plain data types shared across the core. No channel SDK, no I/O.

These are the only shapes that cross the boundary between an adapter
(Telegram/Discord-via-Caspian, or the fake channel) and the core handler.
An adapter's whole job is: turn its platform's event into an InboundMessage,
call the core, turn the core's HandlerResult/Notification back into whatever
its platform needs to actually send.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class InboundMessage:
    """A message arriving on some channel, already normalized.

    channel: opaque string ("telegram", "discord", "fake", ...) — the core
        never branches on this value, it only stores/echoes it.
    conversation_id: the channel's stable per-thread id (Caspian normalizes
        this across platforms; the fake channel makes one up).
    sender_id: best-effort human-readable sender, for display only.
    """

    channel: str
    conversation_id: str
    sender_id: str | None
    text: str


@dataclass(frozen=True)
class HandlerResult:
    """What the core wants said back, in the same conversation."""

    reply_text: str


@dataclass(frozen=True)
class Deadline:
    id: int
    name: str
    due_at: datetime  # aware UTC
    created_at: datetime  # aware UTC
    source_channel: str


@dataclass(frozen=True)
class Notification:
    """A proactive, agent-initiated message the runtime loop must deliver.

    Produced by scheduler.tick()/digest() — never sent by the core itself.
    The adapter looks up how to actually reach (channel, conversation_id)
    and sends `text`.
    """

    channel: str
    conversation_id: str
    text: str
    kind: str  # "alert:24h" | "alert:6h" | "alert:1h" | "digest"
    deadline_id: int | None = None


@dataclass(frozen=True)
class ChannelBinding:
    channel: str
    conversation_id: str
    sender_id: str | None
    last_active_at: datetime
