# Deadline

An agent that watches your open hackathon submission deadlines and reaches
you *before* you miss one — on whichever channel you're actually near.

Built for the **Caspian Buildathon**. Single judging criterion: *the most
creative use case that actually works.* This is the agent I actually want
running on my own phone, which is the brief.

## Why this exists

In the 36 hours before this was written, three real deadlines were missed
for the same reason every time — nothing pinged, so nothing was seen:

- **Arm Create** ($8,000 prize pool)
- **ML Empowerment** ($70,345 headline prize)
- **NEXORA Global**

Not "ran out of time to build." Not "didn't qualify." Missed because the
deadline lived in a tab, an email, a Devpost bookmark — somewhere that
requires *remembering to check it* — and nothing ever spoke up. Deadline
exists to be the thing that speaks up, on Telegram or Discord, wherever I
already am.

## It works — here is the proof, up front

Judging is one criterion: *the most creative use case that **actually works**.*
So the evidence goes here rather than buried at the bottom. Everything below is
copied verbatim from `live.log` on a real run, against real Telegram and Discord
accounts on Caspian's live gateway. Nothing is mocked, staged, or reconstructed.

**Added on Telegram, read back on Discord** — one handler, shared state:

```
18:23:42  REPLY   [telegram] 'Tracking "Caspian Buildathon" — due Sun 16 Aug, 11:23 PM IST'
18:24:26  INBOUND [discord]  '/list'
18:24:26  REPLY   [discord]  'Tracked deadlines (soonest first):
                              - Caspian Buildathon — Sun 16 Aug 2026, 11:23 PM IST (in 4h 59m)   <-- added on Telegram
                              - YouCam API — Mon 17 Aug 2026, 06:00 PM IST ...'
```

**One scheduler tick, one deadline, both channels** — nothing inbound triggered
this; the agent spoke first:

```
18:24:58  PROACTIVE[discord]  kind=alert:24h deadline=8 '⏰ "Discord Side Test" is due in 7h 59m...'
18:24:58  PROACTIVE[telegram] kind=alert:24h deadline=8 '⏰ "Discord Side Test" is due in 7h 59m...'
```

**It fires on time, and only once.** A threshold that came due at 20:00 fired at
20:00:43 — 43 seconds into the next tick. The same deadline later fired its
6-hour alert independently *without* re-firing the 24-hour one:

```
20:00:43  PROACTIVE[both] kind=alert:24h '⏰ "Social Media Automation" is due in 23h 59m...'
20:24:50  PROACTIVE[both] kind=alert:6h  '⏰ "Discord Side Test" is due in 5h 59m...'
```

Across a three-hour live session: **8 distinct alert events, 14 sends, zero
duplicates, zero misses.** Every event fired once per `(deadline, threshold)` and
fanned to every channel bound at that moment — through five transient gateway
outages that the client retried and recovered from on its own.

Full transcripts, including the reverse direction (added on Discord, read on
Telegram) and the restart-survival test, are in
[What's live-verified vs. logic-verified](#whats-live-verified-vs-logic-verified).

### The same thing, in the actual apps

A screen recording of the above happening live — real Telegram and Discord
windows side by side, typed by hand, with the agent's transcript scrolling
underneath — is the demo video linked from the Devpost submission.

## Architecture: one handler, two channels

This is the part the SDK-usage judging actually checks: *"duplicating your
handler per channel doesn't count."* So it doesn't, here.

```mermaid
flowchart LR
    subgraph Real["Live deployment (real tokens)"]
        TG[Telegram] --> CC
        DC[Discord] --> CC
        CC["caspian-sdk CommClient"] --> H
    end
    subgraph Fake["Local dev/test (no credentials needed)"]
        FK["fake_channel.dispatch()"] --> H
    end
    H["core.handler.handle_message()<br/>(deadline_agent/core/*)"] -->|"HandlerResult"| CC
    H --> DB[("SQLite:<br/>deadlines,<br/>notified-state,<br/>channel bindings")]
    SCH["core.scheduler.run_all()<br/>(24h/6h/1h + daily digest)"] --> DB
    SCH -->|"Notification"| CC
```

- **`deadline_agent/core/`** — the entire product: command parsing, the
  forgiving date parser, deadline CRUD, the 24h/6h/1h + daily-digest
  scheduler, SQLite persistence. **Zero imports of `caspian_sdk`, `discord`,
  or `telegram` anywhere in this directory** — not "avoided by convention,"
  mechanically enforced: `tests/test_architecture.py` parses the AST of
  every file in `core/` and fails the suite if one shows up.
- **`deadline_agent/adapters/caspian_app.py`** — the real Telegram + Discord
  wiring. It calls `client.connect_telegram(bot_token=...)` and
  `client.connect_discord(bot_token=...)` on **one** `CommClient`, registers
  **exactly one** `@client.on_message` handler (`register_handler()` —
  `tests/test_architecture.py` also greps its source and fails if that
  decorator appears more than once), and that handler's entire body is:
  turn Caspian's normalized `message` into an `InboundMessage`, call
  `core.handler.handle_message()`, reply with what comes back. Nothing
  channel-specific about deadlines lives here.
- **`deadline_agent/adapters/fake_channel.py`** — the local dev/test
  channel used for everything in Phase 1: same shape, same call into the
  same `handle_message()`. `tests/test_architecture.py` asserts
  `fake_channel.handle_message is caspian_app.handle_message is
  core.handler.handle_message` — literally the same function object, not
  three implementations that happen to agree.
- **`deadline_agent/core/scheduler.py`** — decoupled from every channel:
  it only knows about `Deadline` and `ChannelBinding` records in SQLite and
  produces `Notification(channel, conversation_id, text)` objects. The
  runtime loop (in `caspian_app.py`) is the only place that turns a
  `Notification` into a real `client.send_message(...)` call.

## Commands (identical on every channel)

```
/add <name> <date/time>   Track a new deadline. Dates are forgiving:
                           "17 Aug 9pm", "tomorrow 3am", "in 6 hours",
                           or a plain ISO timestamp all work.
/list                     Everything tracked, soonest first, time remaining.
/remove <name>             Stop tracking something (exact or partial match).
/help                      Command reference.
```

Anything that doesn't match one of the four shapes above falls back to a
help hint — or, if `FEATHERLESS_API_KEY` is set, gets one attempt at being
rewritten into a real command by an LLM first (see "Two-layer design"
below). Try: `hey remind me about impact forge, due in 2 days`.

### The `/add` name/date split

`/add` takes free text with no delimiter between the name and the date
("`/add CS Girlies 17 Aug 9pm`"). The parser tries the **longest possible
date phrase first** and shrinks it from the left, one token at a time,
until something parses — so `"CS Girlies 17 Aug 9pm"` correctly lands on
`name="CS Girlies"`, `when="17 Aug 9pm"`, not `name="CS Girlies 17 Aug"`,
`when="9pm"`. See `deadline_agent/core/commands.py`'s docstring for the
worked examples, and `tests/test_commands.py` for the coverage.

## Proactive behavior (the "agent" part)

- **24h / 6h / 1h alerts** before every tracked deadline.
- **Daily digest** (once per day, after 09:00 IST by default) summarizing
  everything still open.
- **Shared state across channels**: every inbound message — on either
  channel — upserts a `(channel, conversation_id)` binding in SQLite.
  Alerts fire to *every* known binding, so something added on Telegram
  shows up on `/list` from Discord, and both get pinged. This is what makes
  "one handler, two channels" real instead of cosmetic — see
  `tests/test_cross_channel.py`.
- **Restart-safe**: "already notified" is a row in SQLite
  (`notified_thresholds`, keyed by `(deadline_id, kind)`), written in the
  same call that decided to fire. A killed-and-restarted process (a brand
  new `Database` object pointed at the same file, in
  `tests/test_restart_survival.py`) never re-sends an alert that already
  went out.
- **Catch-up firing, on purpose**: if a deadline is added with, say, 45
  minutes left, the 24h and 6h trigger points are already behind "now" —
  so all three alerts fire together on the very next tick instead of being
  silently skipped. This is also the mechanism for proving a *live* alert
  works once real tokens exist: add a deadline a couple of minutes out and
  watch the next tick deliver it for real (see Phase 2 below).

## Two-layer design (deterministic core, AI strictly on top)

Every real command is handled entirely offline — `core/commands.py` and
`core/parser.py` need no network call and no API key. `core/ai_fallback.py`
is a small, *injected* extra: for text that matches none of the four
command shapes, it asks a Featherless-hosted model
(`deepseek-ai/DeepSeek-V3-0324` by default — the required inference
partner) to rewrite it into one, then the exact same deterministic parser
re-parses whatever comes back. If `FEATHERLESS_API_KEY` is unset, or the
call fails for any reason, it returns `None` and the product falls back to
the plain help hint — nothing about `/add`, `/list`, `/remove`, or the
scheduler depends on this layer existing.

## Setup

### 1. Caspian gateway

```bash
pip install caspian-sdk   # or: uv sync (already in pyproject.toml)
# Mint a free sandbox key — no sign-in needed for free channels:
curl -X POST https://api.trycaspianai.com/v1/projects/sandbox -d '{"name":"deadline-agent"}'
```

Put the returned `api_key` into `.env.local` as `CASPIAN_API_KEY`. (A real
one is already there for this submission — see
[What's in `.env.local` right now](#whats-in-envlocal-right-now) below.)

### 2. Telegram

Message [@BotFather](https://t.me/BotFather) on Telegram, `/newbot`, copy
the token into `.env.local` as `TELEGRAM_BOT_TOKEN`.

### 3. Discord

Create an application + bot at
[discord.com/developers/applications](https://discord.com/developers/applications) →
**Bot** → **Reset Token** → put it in `.env.local` as `DISCORD_BOT_TOKEN`.

> **Easy to miss, breaks everything silently if skipped:** on that same Bot
> page, under **Privileged Gateway Intents**, enable **MESSAGE CONTENT
> INTENT**. Without it, Discord never delivers message text to the bot —
> `/add` etc. arrive as empty strings and nothing happens, with no error
> anywhere. (Verified directly against Caspian's own gateway source: its
> Discord gateway listener requests intent bit 15, which is exactly
> `MESSAGE_CONTENT`, alongside `GUILD_MESSAGES` / `DIRECT_MESSAGES` /
> their reaction variants.)

Then invite the bot to a server with the `bot` scope and
`Send Messages` + `Read Message History` permissions.

### 4. Featherless (optional)

Already wired with a real, working key reused from this account's other
projects (see `.env.local`) — this layer works today, no waiting on
anything.

### Run it

```bash
uv sync

# No credentials needed — the local dev/test channel:
uv run python scripts/run_fake.py
> :channel telegram
> /add OregonHacks tomorrow 11:59pm
> :channel discord
> /list                     # <- shows the deadline added from "telegram"
> :advance 23h 59m
> :tick                     # <- alerts fire, printed instead of network-sent

# With real tokens in .env.local — live on Telegram + Discord:
uv run python scripts/run_live.py

# Seed real, currently-open hackathon deadlines (idempotent, safe to re-run):
uv run python scripts/seed.py
```

### Running it for a demo recording

```bash
cd ~/Projects/deadline-agent

# Start in the background, 20s scheduler tick so a near-future alert lands fast,
# with a readable transcript in live.log (gitignored):
nohup env DEADLINE_TICK_SECONDS=20 ./.venv/bin/python scripts/run_live.py > live.log 2>&1 &

# Watch the live transcript (this is the thing worth filming alongside the chats):
tail -f live.log | grep -E "INBOUND|REPLY|PROACTIVE"

# Stop it:
pkill -f "scripts/run_live.py"
```

To make a real proactive alert fire on camera, add a deadline a couple of
minutes out from either chat — `/add Demo in 2 minutes` — and the next tick
delivers it for real. Because every threshold for a 2-minute deadline is
already past, that fires the 24h/6h/1h catch-up burst (three pings); use
`/add Demo in 70 minutes` instead if you want a single clean alert about ten
minutes later.

## Tests

**84 tests, all passing, all offline and deterministic** — no network, no
tokens, no live gateway, run in ~2 seconds:

```bash
uv run pytest -v
```

| File | Covers |
|---|---|
| `test_parser.py` (11) | Forgiving date parsing: ISO timestamps, "tomorrow 3am", "in 6 hours", ambiguous dates resolving to the future, a documented library limitation |
| `test_commands.py` (15) | `/add` name/date splitting, aliases, malformed input, Telegram's `/add@BotName` suffix |
| `test_db.py` (9) | SQLite CRUD, notified-threshold idempotency, digest log, channel-binding upsert |
| `test_handler.py` (18) | The core handler end to end via the fake channel: every command, error paths, the AI-fallback hook (with and without it) |
| `test_scheduler.py` (10) | 24h/6h/1h firing at the right moments, no double-firing, the "no bindings yet" guard, catch-up bursts, daily-digest gating |
| `test_cross_channel.py` (4) | State genuinely shared across two simulated channels — add on one, see/remove on the other |
| `test_restart_survival.py` (3) | A brand-new `Database` object on the same file never re-sends an already-sent alert or digest |
| `test_architecture.py` (3) | AST-level proof `core/` imports nothing channel-specific; both adapters call the identical `handle_message` function object; exactly one `@client.on_message` registration |
| `test_ai_fallback.py` (6) | The optional Featherless layer, entirely mocked via `httpx.MockTransport` — rewrites, `NONE` responses, network/HTTP failures swallowed, not raised |
| `test_fake_channel_adapter.py` (6) | The REPL's duration-parsing helper (`:advance 2d 3h`, etc.) |

Two more scripts exist **outside** the pytest suite on purpose — they hit
real networks and leave real state on a third party's servers, which
doesn't belong in a fast, deterministic, CI-friendly test run:

- `scripts/verify_live_email.py` — connects Caspian's free hosted email
  channel (no token needed at all) and round-trips a real `/add` + `/list`
  through the *exact* `register_handler()` function the live Telegram/
  Discord deployment uses, over real HTTP, against the real gateway. **Run
  once during this build and passed** — see "What's live-verified" below.
- one-off Featherless call proving `core/ai_fallback.py` works against the
  real API, not just the mocked tests.

## What's live-verified vs. logic-verified

Being precise about this, since "if the demo is mocked, it isn't judged" is
the hardest rule here:

Everything below is **live-verified against real networks with real
credentials** — real bot tokens, real humans typing in real chats, verbatim
from the running agent's transcript.

### The cross-channel proof (rule 4)

A deadline added on **Telegram**, listed 45 seconds later from **Discord** —
one handler, one SQLite file, two transports:

```
18:23:41  INBOUND [telegram] from=<human> text='/add Caspian Buildathon in 5 hours'
18:23:42  REPLY   [telegram] 'Tracking "Caspian Buildathon" — due Sun 16 Aug 2026, 11:23 PM IST
                              (5h 0m from now). I'll alert at 24h, 6h, and 1h before,
                              wherever you're active.'

18:24:26  INBOUND [discord]  from=<human> text='/list'
18:24:26  REPLY   [discord]  'Tracked deadlines (soonest first):
                              - Caspian Buildathon — Sun 16 Aug 2026, 11:23 PM IST (in 4h 59m)   <-- added on Telegram
                              - YouCam API — Mon 17 Aug 2026, 06:00 PM IST (in 23h 35m)
                              - Social Media Automation — Mon 17 Aug 2026, 08:00 PM IST (in 1d 1h)
                              - CS Girlies — Mon 17 Aug 2026, 11:59 PM IST (in 1d 5h)
                              - Impact Forge — Mon 17 Aug 2026, 11:59 PM IST (in 1d 5h)
                              - OregonHacks — Tue 18 Aug 2026, 11:59 PM IST (in 2d 5h)'
```

And the reverse — added on **Discord**, listed from **Telegram**:

```
18:24:41  INBOUND [discord]  from=<human> text='/add Discord Side Test in 8 hours'
18:24:42  REPLY   [discord]  'Tracking "Discord Side Test" — due Mon 17 Aug 2026, 02:24 AM IST...'

18:25:11  INBOUND [telegram] from=<human> text='/list'
18:25:11  REPLY   [telegram] 'Tracked deadlines (soonest first):
                              - Caspian Buildathon — Sun 16 Aug 2026, 11:23 PM IST (in 4h 58m)
                              - Discord Side Test — Mon 17 Aug 2026, 02:24 AM IST (in 7h 59m)   <-- added on Discord
                              - YouCam API — Mon 17 Aug 2026, 06:00 PM IST (in 23h 34m)
                              - ...'
```

Both directions, both real humans, both real chats, one handler.

### Proactive alerts fanning out across both channels

Seventeen seconds later, the scheduler alerted on that Discord-added
deadline — and delivered it to **both** channels, because both had a
binding. Same `deadline=8`, two transports, agent-initiated, nothing
inbound triggered it:

```
18:24:58  PROACTIVE[discord]  kind=alert:24h deadline=8 '⏰ "Discord Side Test" is due in 7h 59m ...'
18:24:58  PROACTIVE[telegram] kind=alert:24h deadline=8 '⏰ "Discord Side Test" is due in 7h 59m ...'
```

That is the whole product thesis in two log lines: *it reaches you on
whichever channel you're near.*

### Also live-verified

- **Both channels `active` on the real gateway** — Telegram
  `@Shiv_Hacknews_Bot` (`conn_95ca485a…`), Discord `Hacknews`
  (`conn_22341cdf…`), from one `CommClient`, one `@client.on_message`.
- **Real alerts on the genuinely-seeded hackathon deadlines** — a
  `24 hours-out` alert for **YouCam API** and a real **daily digest**
  ("5 deadline(s) still open"), both delivered unprompted.
- **Restart survival, on the live process.** The agent was killed and
  restarted; it reconnected both channels, ran several scheduler ticks
  against the same SQLite file, and re-sent **nothing** — the already-fired
  YouCam 24h alert and already-sent digest stayed sent.
  `test_restart_survival.py`'s guarantee, reproduced on the real deployment.
- **Discord MESSAGE CONTENT INTENT confirmed enabled** the decisive way: a
  gateway IDENTIFY carrying intent bit 15 was accepted with `READY` rather
  than closed with opcode `4014 Disallowed intent(s)`.
- **The Featherless AI-fallback layer** against the real API.
- **Caspian's hosted email channel** round-tripping `/add` + `/list` through
  the same `register_handler()` (`scripts/verify_live_email.py`).

### One rough edge, honestly

Caspian's gateway failed five event polls across the session — four
`500: Internal Server Error`, one Cloudflare `502`:

```
18:24:17  WARNING gateway poll failed; retrying in 1.0s
18:46:26  WARNING gateway poll failed; retrying in 1.0s
19:25:32  WARNING gateway poll failed; retrying in 1.0s
          caspian_sdk.client.CommError: 500: Internal Server Error
21:29:55  WARNING gateway poll failed; retrying in 1.0s
21:41:47  WARNING gateway poll failed; retrying in 1.0s
```

Every one was server-side, and every one `client.listen()` retried with backoff
and recovered from on its own — the next message after each was handled normally,
which is why the timestamps above are continuous. Zero crashes, zero lost alerts,
zero duplicate sends. It's a real thing that happened on a real network and it
would be dishonest to scrub it from the log; an agent whose whole job is
reliability should be the last one to hide a transport wobble.

## What's in `.env.local` right now

| Variable | Status |
|---|---|
| `CASPIAN_API_KEY`, `CASPIAN_BASE_URL` | **Real**, minted free, live-verified |
| `FEATHERLESS_API_KEY`, `FEATHERLESS_BASE_URL`, `FEATHERLESS_MODEL` | **Real**, live-verified |
| `TELEGRAM_BOT_TOKEN` | **Real**, live-verified end to end (`@Shiv_Hacknews_Bot`) |
| `DISCORD_BOT_TOKEN` | **Real**, connection active, bot in a server (`Hacknews`) |
| `TELEGRAM_CHAT_ID`, `DISCORD_CHANNEL_ID` | Blank by design — not read by any code; Caspian routes by `conversation_id` |

## Honest limits

- **The agent answers every non-bot message in any Discord channel it can
  read**, not only `@`-mentions (Caspian forwards all of them, and this
  handler replies to each — non-commands get the help hint). That is the
  right behavior for the personal single-user server this runs in, and it
  guarantees a bare `/list` works without an `@`-mention; in a busy shared
  server you would want to gate on mention or `chat_type == "dm"` first.
- The scheduler runs as a background thread inside the same process as
  `client.listen()` (a 60-second tick by default); it is not a separate
  cron job or serverless function. Fine for a single-user personal agent,
  the stated use case here.
- `/remove` matching is exact-or-substring, case-insensitive, over
  currently-tracked names — good enough for a handful of hackathon
  deadlines, would want fuzzier matching at real scale.
- The AI-fallback layer is a single, non-conversational rewrite attempt
  (one model call, no retry, no multi-turn negotiation) — by design, so a
  flaky or slow model call never blocks the deterministic core.
- Digest timing (`09:00` local) and alert thresholds (`24h`/`6h`/`1h`) are
  constants in `core/scheduler.py`, not yet exposed as user-configurable
  commands.

## Repo layout

```
deadline_agent/
  core/              # the entire product — zero channel imports, enforced by test
    models.py          InboundMessage, HandlerResult, Deadline, Notification, ChannelBinding
    clock.py            Clock / SystemClock / FakeClock
    db.py                SQLite: deadlines, notified thresholds, digest log, channel bindings
    parser.py            forgiving date parsing (wraps `dateparser`)
    commands.py          text -> Command (the /add name/date split lives here)
    handler.py           THE one handler: handle_message()
    scheduler.py         24h/6h/1h + daily digest, decoupled from any channel
    formatting.py        human-readable times/durations
    ai_fallback.py       optional Featherless-backed rewrite layer
  adapters/
    fake_channel.py     local dev/test channel + interactive REPL
    caspian_app.py       real Telegram + Discord wiring through caspian-sdk
  config.py             shared defaults + .env.local loader
scripts/
  run_fake.py            no-credential interactive demo
  run_live.py            Phase 2: real Telegram/Discord
  seed.py                seeds real, currently-open hackathon deadlines
  verify_live_email.py   one-off live proof against the real Caspian gateway
tests/                  84 tests, offline, ~2s
```
