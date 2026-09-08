"""Load existing merit totals into the bot from a CSV export.

Backdating is a one way door, so this prints what it would change and writes
nothing until you pass --apply. Run it with the bot stopped.

    python tools/import_merit.py totals.csv
    python tools/import_merit.py totals.csv --apply

The merit column is read as a total to set. Pass --add to treat it as an
amount to add instead, which is what a partial source such as an oath scrape
needs so it does not overwrite totals loaded from somewhere else. --add is
not idempotent, so do not run the same file through it twice.

The CSV needs a column identifying the member and at least one column to set.
Column names are matched loosely, so an export straight out of a spreadsheet
usually works as it is.

    member column   user_id, userid, discord_id, discord, member, id, mention
    merit column    merit, merit_total, total, points, score
    oath column     oath, oath_taken, sworn
    uniform column  uniform, skin, uniform_set
    note column     note, notes, comment, reason

Values for oath and uniform are read as yes, y, true, 1, x and checkmarks.
A member can be given as a raw ID or as a Discord mention.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from abex.db import Database  # noqa: E402
from abex.ranks import entitled_rank  # noqa: E402

MEMBER_COLUMNS = ("user_id", "userid", "discord_id", "discordid", "discord", "member", "id", "mention")
MERIT_COLUMNS = ("merit", "merit_total", "total", "points", "score")
OATH_COLUMNS = ("oath", "oath_taken", "sworn")
UNIFORM_COLUMNS = ("uniform", "skin", "uniform_set")
NOTE_COLUMNS = ("note", "notes", "comment", "reason")

TRUE_VALUES = {"y", "yes", "true", "t", "1", "x", "✓", "✔", "done", "complete"}
FALSE_VALUES = {"", "n", "no", "false", "f", "0", "-", "none", "na", "n/a"}

MENTION = re.compile(r"<@!?(\d{15,25})>")
SNOWFLAKE = re.compile(r"(\d{15,25})")


class ImportError_(RuntimeError):
    pass


@dataclass
class Row:
    line: int
    user_id: int
    merit: int | None
    oath: bool | None
    uniform: bool | None
    note: str | None


def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def pick_column(headers: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in headers:
            return headers[candidate]
    return None


def parse_flag(raw: str | None) -> bool | None:
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return None if value == "" else False
    raise ImportError_(f"cannot read {raw!r} as a yes or no")


def parse_user_id(raw: str) -> int:
    mention = MENTION.search(raw)
    if mention:
        return int(mention.group(1))
    plain = SNOWFLAKE.search(raw)
    if plain:
        return int(plain.group(1))
    raise ImportError_(f"no Discord ID in {raw!r}")


def parse_merit(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None
    cleaned = raw.strip().replace(",", "").replace("+", "")
    try:
        return max(0, int(float(cleaned)))
    except ValueError as exc:
        raise ImportError_(f"cannot read {raw!r} as a merit total") from exc


def read_rows(path: Path) -> tuple[list[Row], list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ImportError_(f"{path} has no header row")
        headers = {normalise(name): name for name in reader.fieldnames if name}

        member_col = pick_column(headers, MEMBER_COLUMNS)
        if member_col is None:
            raise ImportError_(
                f"{path} has no member column. Looked for any of: {', '.join(MEMBER_COLUMNS)}. "
                f"Found: {', '.join(reader.fieldnames)}"
            )
        merit_col = pick_column(headers, MERIT_COLUMNS)
        oath_col = pick_column(headers, OATH_COLUMNS)
        uniform_col = pick_column(headers, UNIFORM_COLUMNS)
        note_col = pick_column(headers, NOTE_COLUMNS)

        if not any((merit_col, oath_col, uniform_col)):
            raise ImportError_(f"{path} has nothing to import, no merit, oath or uniform column")

        rows: list[Row] = []
        problems: list[str] = []
        seen: dict[int, int] = {}

        for line, raw in enumerate(reader, start=2):
            identifier = (raw.get(member_col) or "").strip()
            if not identifier:
                continue
            try:
                user_id = parse_user_id(identifier)
                merit = parse_merit(raw.get(merit_col)) if merit_col else None
                oath = parse_flag(raw.get(oath_col)) if oath_col else None
                uniform = parse_flag(raw.get(uniform_col)) if uniform_col else None
            except ImportError_ as exc:
                problems.append(f"line {line}: {exc}")
                continue

            if user_id in seen:
                problems.append(f"line {line}: {user_id} already appeared on line {seen[user_id]}")
                continue
            seen[user_id] = line

            note = (raw.get(note_col) or "").strip() if note_col else None
            rows.append(Row(line, user_id, merit, oath, uniform, note or None))

    return rows, problems


async def run(path: Path, db_path: str, apply: bool, officer_id: int | None, add: bool) -> int:
    rows, problems = read_rows(path)

    if problems:
        print(f"{len(problems)} row(s) could not be read:")
        for problem in problems:
            print(f"  {problem}")
        print()

    if not rows:
        print("Nothing to import.")
        return 1 if problems else 0

    db = Database(db_path)
    await db.connect()
    try:
        changes: list[str] = []
        for row in rows:
            before = await db.get_member(row.user_id)
            old_merit = before.merit if before else 0
            old_oath = before.oath if before else False
            old_uniform = before.uniform if before else False

            if row.merit is None:
                merit = old_merit
            elif add:
                merit = old_merit + row.merit
            else:
                merit = row.merit
            oath = row.oath if row.oath is not None else old_oath
            uniform = row.uniform if row.uniform is not None else old_uniform

            if (merit, oath, uniform) == (old_merit, old_oath, old_uniform):
                continue

            rank = entitled_rank(merit, oath, uniform)
            parts = []
            if merit != old_merit:
                arrow = f"merit {old_merit} to {merit}"
                parts.append(f"{arrow} (+{row.merit})" if add and row.merit else arrow)
            if oath != old_oath:
                parts.append(f"oath {'set' if oath else 'cleared'}")
            if uniform != old_uniform:
                parts.append(f"uniform {'set' if uniform else 'cleared'}")
            changes.append(f"  {row.user_id}: {', '.join(parts)} -> {rank.name}")

            if apply:
                if row.oath is not None:
                    await db.set_flag(row.user_id, "oath", row.oath)
                if row.uniform is not None:
                    await db.set_flag(row.user_id, "uniform", row.uniform)
                if row.merit is not None:
                    reason = row.note or f"Backdated from {path.name}"
                    if add:
                        await db.add_merit(row.user_id, row.merit, "import", reason, officer_id)
                    else:
                        await db.set_merit(row.user_id, merit, officer_id, reason)
                await db.set_rank(row.user_id, rank.key)

        print(f"Read {len(rows)} row(s) from {path}.")
        if not changes:
            print("Nothing would change, the database already matches.")
        else:
            print(f"{'Applied' if apply else 'Would change'} {len(changes)} member(s):")
            print("\n".join(changes))

        if not apply and changes:
            print("\nThis was a dry run. Nothing was written. Pass --apply to commit it.")
    finally:
        await db.close()

    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", type=Path, help="CSV export holding the existing totals")
    parser.add_argument("--apply", action="store_true", help="write the changes, default is a dry run")
    parser.add_argument(
        "--add",
        action="store_true",
        help="treat the merit column as an amount to add rather than a total to set. "
        "Use this for a partial source such as an oath scrape, so it does not "
        "overwrite totals already loaded from elsewhere.",
    )
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/abex.db"), help="database file")
    parser.add_argument(
        "--officer",
        type=int,
        default=None,
        help="Discord ID to record as the officer behind the import",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"{args.csv} does not exist.", file=sys.stderr)
        return 2
    try:
        return asyncio.run(run(args.csv, args.db, args.apply, args.officer, args.add))
    except ImportError_ as exc:
        print(f"Could not read {args.csv}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
