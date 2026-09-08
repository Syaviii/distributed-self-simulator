"""The backdating importer.

This writes to real member records, so the parsing is worth pinning down.
"""

import pytest
import pytest_asyncio

from abex.db import Database
from tools.import_merit import ImportError_, parse_flag, parse_merit, parse_user_id, read_rows, run


@pytest_asyncio.fixture
async def db_path(tmp_path):
    path = tmp_path / "import.db"
    database = Database(path)
    await database.connect()
    await database.close()
    return path


def write(tmp_path, text):
    path = tmp_path / "in.csv"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("123456789012345678", 123456789012345678),
        ("<@123456789012345678>", 123456789012345678),
        ("<@!123456789012345678>", 123456789012345678),
        ("  123456789012345678  ", 123456789012345678),
    ],
)
def test_user_ids_are_read_from_ids_and_mentions(raw, expected):
    assert parse_user_id(raw) == expected


def test_a_name_without_an_id_is_rejected():
    with pytest.raises(ImportError_):
        parse_user_id("SomePlayer")


@pytest.mark.parametrize("raw", ["y", "YES", "true", "1", "x", "✓", "Done"])
def test_yes_values(raw):
    assert parse_flag(raw) is True


@pytest.mark.parametrize("raw", ["n", "NO", "false", "0", "-", "n/a"])
def test_no_values(raw):
    assert parse_flag(raw) is False


def test_a_blank_flag_means_leave_it_alone():
    assert parse_flag("") is None
    assert parse_flag(None) is None


def test_nonsense_flags_are_rejected():
    with pytest.raises(ImportError_):
        parse_flag("maybe")


@pytest.mark.parametrize(
    "raw,expected", [("5", 5), ("1,205", 1205), ("+10.0", 10), ("", None), ("  ", None), ("-4", 0)]
)
def test_merit_values(raw, expected):
    assert parse_merit(raw) == expected


def test_headers_are_matched_loosely(tmp_path):
    path = write(tmp_path, "Discord ID,Merit Total,Oath\n<@1234567890123456789>,50,yes\n")
    rows, problems = read_rows(path)
    assert not problems
    assert rows[0].user_id == 1234567890123456789
    assert rows[0].merit == 50
    assert rows[0].oath is True


def test_a_file_with_no_member_column_is_rejected(tmp_path):
    path = write(tmp_path, "name,merit\nsomeone,5\n")
    with pytest.raises(ImportError_):
        read_rows(path)


def test_a_file_with_nothing_to_set_is_rejected(tmp_path):
    path = write(tmp_path, "user_id,name\n1234567890123456789,someone\n")
    with pytest.raises(ImportError_):
        read_rows(path)


def test_duplicates_are_reported_not_silently_applied(tmp_path):
    path = write(
        tmp_path,
        "user_id,merit\n1234567890123456789,10\n1234567890123456789,900\n",
    )
    rows, problems = read_rows(path)
    assert len(rows) == 1 and rows[0].merit == 10
    assert any("already appeared" in p for p in problems)


async def test_dry_run_writes_nothing(db_path, tmp_path, capsys):
    path = write(tmp_path, "user_id,merit,oath,uniform\n1234567890123456789,300,y,y\n")
    await run(path, str(db_path), apply=False, officer_id=None, add=False)
    assert "dry run" in capsys.readouterr().out

    db = Database(db_path)
    await db.connect()
    assert await db.get_member(1234567890123456789) is None
    await db.close()


async def test_apply_sets_merit_flags_and_rank(db_path, tmp_path):
    path = write(tmp_path, "user_id,merit,oath,uniform\n1234567890123456789,300,y,y\n")
    await run(path, str(db_path), apply=True, officer_id=99, add=False)

    db = Database(db_path)
    await db.connect()
    member = await db.get_member(1234567890123456789)
    assert (member.merit, member.oath, member.uniform) == (300, True, True)
    assert member.rank_key == "district_official"
    await db.close()


async def test_the_gate_still_applies_to_imported_members(db_path, tmp_path):
    path = write(tmp_path, "user_id,merit\n1234567890123456789,300\n")
    await run(path, str(db_path), apply=True, officer_id=None, add=False)

    db = Database(db_path)
    await db.connect()
    member = await db.get_member(1234567890123456789)
    assert member.merit == 300
    assert member.rank_key == "group_loyalist", "no oath or uniform means no advancement"
    await db.close()


async def test_totals_mode_is_idempotent(db_path, tmp_path):
    path = write(tmp_path, "user_id,merit\n1234567890123456789,120\n")
    await run(path, str(db_path), apply=True, officer_id=None, add=False)
    await run(path, str(db_path), apply=True, officer_id=None, add=False)

    db = Database(db_path)
    await db.connect()
    assert (await db.get_member(1234567890123456789)).merit == 120
    await db.close()


async def test_add_mode_accumulates_instead_of_overwriting(db_path, tmp_path):
    totals = write(tmp_path, "user_id,merit\n1234567890123456789,100\n")
    await run(totals, str(db_path), apply=True, officer_id=None, add=False)

    oath = tmp_path / "oath.csv"
    oath.write_text("user_id,merit,oath\n1234567890123456789,2,yes\n", encoding="utf-8")
    await run(oath, str(db_path), apply=True, officer_id=None, add=True)

    db = Database(db_path)
    await db.connect()
    member = await db.get_member(1234567890123456789)
    assert member.merit == 102, "the oath should add to the total, not replace it"
    assert member.oath
    await db.close()
