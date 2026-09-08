# Abexilian Remnant merit bot

Tracks merit, runs the promotion ladder and renders an Abexilian ID card for
every member. Built from the pinned promotion guide, so the thresholds, merit
sources and caps in the code are the ones the server already publishes.

## What it does

Two systems, kept apart on purpose.

**The merit ladder is automated.** Loyalist through Precinct Official, eleven
ranks on fixed merit thresholds. Officers log activity, the bot adds merit,
recalculates the rank, swaps the Discord role and announces the promotion.

**Appointments are manual.** Regional Command and above, plus the whole Council
of Governors track, are conferred rather than earned. The bot records them and
shows them on the profile card. It never hands one out on its own.

## The Group Loyalist gate

The guide says Group Loyalist requires a uniform and oath to advance further,
so the bot enforces it. A member sitting on 300 merit without both flags stays
at Group Loyalist, and their profile says so in plain words rather than
silently doing nothing. The moment an officer records both, the backlog is
released and they jump straight to the rank their merit earned.

## Caps

- One time sources (oath, uniform, roleplay character) can only ever be
  credited once per member.
- Event attendance is one credit per member per UTC day.
- Tithes convert at 1 merit per 1000, capped at 20 merit per rolling seven
  days. Going over is rejected with the amount that did not fit, not silently
  swallowed.

Every cap is checked against the merit log, so the answer is always the same
one an audit would give.

## Setup

1. Create the application at https://discord.com/developers/applications, add a
   bot user and copy the token.
2. Turn on the **Server Members** privileged intent for the bot.
3. Invite it with the `bot` and `applications.commands` scopes and the
   **Manage Roles** permission.
4. In the server settings, drag the bot's own role **above** every rank role.
   Discord will not let it assign a role that sits higher than its own.

```
git clone <this repo>
cd distributed-self-simulator
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env            # add your token
cp config.example.json config.json
python bot.py
```

## Configuration

`config.json` holds everything server specific. No IDs live in source, so a
restructure means editing one file.

| Key | What it does |
| --- | --- |
| `guild_id` | Server the commands sync to |
| `officer_roles` | Roles allowed to log merit, grant awards, set flags |
| `command_roles` | Roles allowed to record appointments and correct totals |
| `rank_roles` | Rank key to Discord role ID |
| `appointment_roles` | Appointment key to Discord role ID |
| `promotion_channel` | Where promotions are announced |
| `audit_channel` | Optional mirror of every merit change |
| `manage_roles` | Set false to track ranks without touching roles |
| `demote_on_merit_loss` | Set false to make ranks permanent once reached |

Emoji are already filled in from the promotion guide. Rank and appointment role
IDs start blank. Any rank you leave blank is tracked but not roled, so you can
roll the bot out one tier at a time.

Server owners and administrators always pass the permission checks, so a fresh
install cannot lock itself out.

## Commands

**Everyone**

| Command | Does |
| --- | --- |
| `/profile [member]` | The ID card: rank, merit, progress to next, awards, appointments |
| `/merit check` | Your own card, only visible to you |
| `/leaderboard [size]` | Top members by merit |
| `/ranks` | The ladder and its thresholds |

**Officers**

| Command | Does |
| --- | --- |
| `/merit log <member> <activity> [note]` | Credit from the standard table, caps enforced |
| `/merit tithe <member> <amount>` | Converts the amount tithed, tracks the weekly cap |
| `/merit grant <member> <amount> <reason>` | Off table grant, reason required |
| `/merit revoke <member> <amount> <reason>` | Remove merit, stops at zero |
| `/merit history <member> [entries]` | Full audit trail |
| `/roster oath <member> [taken]` | Record or clear the branch oath |
| `/roster uniform <member> [worn]` | Record or clear the division uniform |
| `/roster award <member> <name> [note]` | Grant an award |
| `/roster unaward <member> <name>` | Remove one |

**High Command**

| Command | Does |
| --- | --- |
| `/merit set <member> <total> <reason>` | Force a total, logged as a correction |
| `/roster appoint <member> <appointment> [note]` | Record an appointment |
| `/roster unappoint <member> <appointment>` | Remove one |
| `/roster sync [member]` | Re-apply rank roles from stored merit |

`/roster sync` with no member is the migration path. Import totals with
`/merit set`, then run it once and every role lands where it belongs.

## Development

```
pip install pytest pytest-asyncio
python -m pytest
```

The suite covers the ladder, the gate, cap enforcement, demotion behaviour and
a startup smoke test that builds the whole command tree. The tree test exists
because a name collision between a command and a group only surfaces at
startup, which on a live bot means in front of the whole server.

## Notes

- `abex/ranks.py` is the single source of truth. Changing a threshold or adding
  a merit source means editing that file and nothing else.
- The merit log is append only. `/merit set` writes the difference as a
  correction rather than editing history.
- The bot deliberately does not touch Supreme Command roles. Those are a
  handful of people who get roled by hand, and there is no reason to give a
  merit tracker that blast radius.
