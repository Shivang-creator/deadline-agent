"""Optional AI layer on top of the deterministic core — the two-layer split:
core/commands.py handles every real command entirely offline, no network, no
API key required. This module is a small, *injectable* fallback for
messages that don't match any known command shape (someone typing "remind me
about impact forge, due in 2 days" instead of the exact /add syntax): it
asks a Featherless-hosted model to rewrite free text into one of the four
supported commands, and handler.py re-parses whatever comes back with the
exact same deterministic parser used everywhere else.

If FEATHERLESS_API_KEY is unset, or the request fails for any reason, the
built fallback returns None and the core silently uses the plain help hint
instead. The product works fully offline with this layer entirely absent —
see handler.handle_message()'s `ai_fallback=None` default.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

logger = logging.getLogger("deadline_agent.ai_fallback")

SYSTEM_PROMPT = """You translate a user's free-form message into ONE of these exact command shapes, and output ONLY that command with nothing else - no explanation, no markdown, no quotes:

/add <name> <date or time phrase>
/list
/remove <name>
/help

Rules:
- If the message describes a deadline to track, output /add with the clearest short name and the date/time phrase taken from the message (verbatim where possible, e.g. "in 2 days", "tomorrow 9pm").
- If the message asks what's tracked / due / upcoming, output /list.
- If it asks to stop tracking or delete something, output /remove <name>.
- If you cannot confidently map it to one of these four shapes, output exactly: NONE
Output nothing else. One line only."""


def build_featherless_fallback(
    api_key: str,
    base_url: str,
    model: str,
    *,
    http_client: httpx.Client | None = None,
    timeout: float = 8.0,
) -> Callable[[str], str | None]:
    """Returns a callable suitable for handler.handle_message(ai_fallback=...).

    `http_client` is injectable so tests can pass one built on
    httpx.MockTransport instead of hitting the real network.
    """
    client = http_client or httpx.Client(timeout=timeout)
    endpoint = f"{base_url.rstrip('/')}/chat/completions"

    def fallback(raw_text: str) -> str | None:
        text = (raw_text or "").strip()
        if not text:
            return None
        try:
            response = client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": text},
                    ],
                    "max_tokens": 60,
                    "temperature": 0,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            logger.warning("Featherless fallback failed; ignoring", exc_info=True)
            return None
        if not content or content.strip().upper() == "NONE":
            return None
        return content.splitlines()[0].strip()

    return fallback
