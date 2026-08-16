# Deadline — Caspian Buildathon submission

## Project name
```
Deadline
```

## Elevator pitch
```
I missed three hackathon deadlines in 36 hours because nothing told me. Deadline is the agent that fixes that — it watches your submissions and reaches you on whichever channel you're near. One handler, Telegram and Discord, and it messages you first.
```

## Built With
```
caspian-sdk, python, sqlite, telegram, discord, featherless-ai, pytest
```

---

## About the project

### I built the agent I actually needed, because I'd just been burned

On 15 August I lost three hackathons — Arm Create, ML Empowerment, NEXORA Global — not because the work wasn't done, but because nothing pinged me. I found out they'd closed by scrolling past them the next morning.

Caspian's brief says *"build the agent you actually want running."* This is it, literally. Deadline tracks my open submissions and messages me **first** — 24 hours out, 6 hours out, 1 hour out — wherever I happen to be. It is running right now, and the deadlines in it are real ones I'm working toward tonight.

### One handler, two channels — and here's the proof

The rule is that the agent must run on two channels through a single handler, and duplicating a handler per channel doesn't count. So this was designed for that constraint from the first commit:

- `deadline_agent/core/` holds **100% of the product logic** — commands, parsing, scheduling, storage — and imports **zero** channel code. Not "written that way for now": `tests/test_architecture.py` parses the AST of every file in `core/` and **fails the build** if `caspian_sdk`, `discord`, or `telegram` ever appears in an import.
- `adapters/caspian_app.py` connects both channels on one `CommClient` with exactly **one** `@client.on_message` — also AST-asserted to appear precisely once.
- The offline test harness and the live Caspian wiring dispatch into the **same function object**, asserted with `is`, not "two implementations that happen to agree."

**The live transcript, verbatim:**

```
18:23:42 REPLY   [telegram] 'Tracking "Caspian Buildathon" — due Sun 16 Aug, 11:23 PM IST'
18:24:26 INBOUND [discord]  '/list'
18:24:26 REPLY   [discord]  'Tracked deadlines (soonest first):
                             - Caspian Buildathon — Sun 16 Aug 2026, 11:23 PM IST (in 4h 59m)   <-- added on Telegram
                             - YouCam API — Mon 17 Aug 2026, 06:00 PM IST ...'
```

And the reverse:

```
18:24:41 INBOUND [discord]  '/add Discord Side Test in 8 hours'
18:25:11 INBOUND [telegram] '/list'
18:25:11 REPLY   [telegram] '- Discord Side Test — Mon 17 Aug 2026, 02:24 AM IST (in 7h 59m)'   <-- added on Discord
```

### The single line I'd point a judge at

One scheduler tick. One deadline. Two transports. Nothing inbound triggered it:

```
18:24:58 PROACTIVE[discord]  kind=alert:24h deadline=8 '⏰ "Discord Side Test" is due in 7h 59m...'
18:24:58 PROACTIVE[telegram] kind=alert:24h deadline=8 '⏰ "Discord Side Test" is due in 7h 59m...'
```

Same millisecond, same deadline id, fanned to both bindings by one handler. That is what "one handler, two channels" means when it's real rather than described.

### It's an agent, not a chatbot

The commands are the boring half. The half that matters is that **it speaks first**:

- Automatic alerts at 24h / 6h / 1h before anything tracked
- A daily digest of what's still open
- Alerts fan to every channel you've used, so it reaches you where you are
- **Restart-safe** — I killed the running process mid-session and restarted it; it reconnected both channels, ran four scheduler ticks against the same database, and re-fired **zero** already-sent alerts

Commands work identically everywhere: `/add <name> <when>` (forgiving dates — *"17 Aug 9pm"*, *"tomorrow 3am"*, *"in 6 hours"*), `/list`, `/remove`, `/help`.

### 84 tests

`pytest` — 84 passing, all offline and deterministic, ~2s. Date parsing edge cases, scheduler firing windows and non-double-firing, catch-up bursts, daily-digest gating, cross-channel state sharing, restart survival, and the two architectural guarantees above. A fake in-memory channel adapter exercises the entire product end to end without touching a network, which is how the whole thing was built and verified before a single real token existed.

### What went wrong, left in

The Caspian gateway returned a `500: Internal Server Error` on one event poll during live testing. `client.listen()` retried with backoff and recovered on its own — the next Discord message was handled normally. I'm reporting it rather than scrubbing it, because an agent whose entire job is reliability should be honest about the one time its transport wasn't.

### Honest limits

- Deadlines are entered by hand. It doesn't scrape Devpost — that was a deliberate scope call, and it's the obvious next feature.
- Alerts reach channels you've already spoken on; the agent can't cold-open a conversation Telegram hasn't permitted.
- Times are stored in a fixed timezone; multi-timezone users would need real per-user preferences.
- Featherless is wired in as an optional natural-language fallback for unparsed input, but the core command path is deliberately deterministic — a scheduler that decides when to alert you shouldn't be a model call.

---

## Try it out
```
https://github.com/Shivang-creator/deadline-agent
```
