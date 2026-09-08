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

## Branches and ladders

The Remnant has four branches: the Armed Forces, COMPAO, the Civil Services and
the Regional Government. A member may belong to all four at once, one division
in each, so rank is not a single role. Three of those ladders exist as Discord
roles today and the bot gives a member their rank on **every** ladder they
belong to, at one shared merit total. Someone in both the Commission and the
Civil Service on 210 merit is a Section Official and a Supervisor at the same
time, and their profile card names both.

Ladder roles from branches a member is not in get stripped on sync, which is
what makes a branch transfer clean up after itself.

The Army has no ladder roles of its own and falls through to the base ranks,
which the server's own quick guide calls the Bureaucracy structure. The
Regional Government does not promote on merit at all: Prefect, Governor,
Siridar and Grand Siridar are appointments.

| Merit | Base | COMPAO | Civil Service |
| --- | --- | --- | --- |
| 0 | Loyalist | Loyalist | Intern |
| 2 | Junior Loyalist | Junior Loyalist | Junior Clerk |
| 10 | Senior Loyalist | Senior Loyalist | Senior Clerk |
| 15 | Group Loyalist | Group Loyalist | Administrative Clerk |
| 25 | Section Loyalist | Section Loyalist | Supervisory Clerk |
| 35 | Unit Loyalist | Unit Loyalist | Chief Clerk |
| 75 | Group Official | Group Official | Probationary Supervisor |
| 135 | Service Official | Service Official | Junior Supervisor |
| 210 | Section Official | Section Official | Supervisor |
| 300 | District Official | District Official | Senior Supervisor |
| 400 | Precinct Official | Precinct Official | Chief Supervisor |

COMPAO uses the same titles as the base ladder but its own set of roles. The
Civil Service renames every step, so a profile card, a promotion announcement
and `/ranks` all show a member the titles their own branch uses.

Branch membership comes from `branch_tracks` in the config. The Enlightenment
Group, the Department of Information and Culture and the Abexilian Security
Bureau are the divisions that put someone on the Commission ladder, and the
Select Committee is its leadership. The ministries, the Diplomatic Corps and
Civil Services Unassigned are the Civil Service ladder.

The government structure chart lists eleven ladders, one per division, with
per-ministry titles. Only three exist as Discord roles, so only three are
implemented. Adding a fourth means creating its roles and adding a name map to
`abex/ranks.py`.

The bot also keeps the `Junior Bureaucrat` and `Senior Bureaucrat` tier roles in
step with the rank, so crossing 75 merit swaps one for the other.

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

Step 4 is not optional and it is the thing that will bite you. Discord ignores
Administrator for role hierarchy: a bot cannot touch any role positioned above
its own, no matter what permissions it holds. The bot's role has to sit above
`Precinct Official` and its COMPAO and Civil Service equivalents, or every rank
change fails and the bot says so on every command.

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
| `rank_roles` | Track to rank key to Discord role ID |
| `appointment_roles` | Track to appointment key to Discord role ID, falling back to base |
| `tier_roles` | Junior and Senior Bureaucrat role IDs |
| `branch_tracks` | Branch role ID to the ladder that branch promotes on |
| `promotion_channel` | Where promotions are announced |
| `audit_channel` | Optional mirror of every merit change |
| `manage_roles` | Set false to track ranks without touching roles |
| `demote_on_merit_loss` | Set false to make ranks permanent once reached |

Emoji are already filled in from the promotion guide. Rank and appointment role
IDs start blank. Any rank you leave blank is tracked but not roled, so you can
roll the bot out one tier at a time.

Server owners and administrators always pass the permission checks, so a fresh
install cannot lock itself out.

`officer_roles` deliberately excludes `Senior Bureaucrat`. That role is the tier
role the bot hands out at 75 merit, so listing it would let anyone promote
themselves into the power to log merit. The guide defines Officer as Municipal
Leader and above, which is Regional Command, and that is where the line sits.
There is a test asserting no tier role appears in either permission list.

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

## Backdating existing merit

Role changes are switched off in the shipped config (`manage_roles: false`)
while existing totals are loaded, so the bot records everything and moves no
roles. Turn it back on once the numbers are right.

`tools/import_merit.py` loads totals from a CSV. It prints what it would change
and writes nothing until you pass `--apply`.

```
python tools/import_merit.py totals.csv            # dry run
python tools/import_merit.py totals.csv --apply
```

Column names are matched loosely, so a spreadsheet export usually works as it
is. A member can be a raw ID or a Discord mention. Duplicate rows and
unreadable IDs are reported rather than silently applied, and the gate still
applies, so importing 300 merit with no oath recorded leaves that member at
Group Loyalist exactly as the rules say.

The merit column is read as a total to set, which makes a re-run a no-op. Pass
`--add` to treat it as an amount to add instead, which is what a partial source
needs so it does not overwrite totals loaded from elsewhere. `--add` is not
idempotent, so do not run the same file through it twice.

`tools/scrape_oaths.py` reads the oath channel and writes the same CSV format,
one row per member with the earliest oath kept:

```
export DISCORD_TOKEN=...
python tools/scrape_oaths.py <channel id> > oaths.csv
python tools/import_merit.py oaths.csv --add
```

## Development

```
pip install pytest pytest-asyncio
python -m pytest
```

The suite covers the ladder, the gate, cap enforcement, demotion behaviour,
branch resolution across the three ladders including members in two branches at
once, the importer, and a startup smoke test that builds the whole command
tree. The tree test exists because a name collision between a
command and a group only surfaces at startup, which on a live bot means in front
of the whole server.

It also checks the shipped `config.abexilian.json` end to end: every rank on
every track resolves to a real role, no two tracks share a role, and no tier
role has leaked into the permission lists.

## Notes

- `abex/ranks.py` is the single source of truth. Changing a threshold or adding
  a merit source means editing that file and nothing else.
- The merit log is append only. `/merit set` writes the difference as a
  correction rather than editing history.
- The bot deliberately does not touch Supreme Command roles. Those are a
  handful of people who get roled by hand, and there is no reason to give a
  merit tracker that blast radius.
- The bot only needs Manage Roles. It currently holds Administrator on the
  server, which is far more than a merit tracker should carry.
- Ministry of Justice appears in the structure chart but has no Discord role,
  and neither do Vice Chancellor, Chief of Operations, or the two COMPAO
  Director posts. They cannot be recorded until the roles exist.
- Two role names differ from the guide. The server has `Grand Marshall` and
  `Abexilian Marshall` where the guide writes Marshal, and
  `Chairman of the Commission` where the guide writes Chairman of COMPAO. The
  config follows the server. There is no `Deputy Chairman of COMPAO` role, so
  that appointment is recorded without a role until one exists.
- `(Civil Service) Supervisory Clerk)` has a stray closing paren in its role
  name. The config matches the server as it is, but it is worth renaming so it
  does not show up that way on profile cards.
