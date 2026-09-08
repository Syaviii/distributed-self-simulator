"""Storage and cap enforcement."""

import pytest
import pytest_asyncio

from abex.db import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


async def test_new_member_starts_empty(db):
    member = await db.ensure_member(1)
    assert member.merit == 0
    assert member.rank_key == "loyalist"
    assert not member.oath and not member.uniform


async def test_ensure_member_is_idempotent(db):
    first = await db.ensure_member(1)
    await db.add_merit(1, 5, "event")
    second = await db.ensure_member(1)
    assert second.merit == 5
    assert second.first_seen == first.first_seen


async def test_merit_accumulates(db):
    await db.add_merit(1, 8, "operation")
    member = await db.add_merit(1, 10, "raid")
    assert member.merit == 18


async def test_revoke_clamps_at_zero_and_log_agrees(db):
    await db.add_merit(1, 5, "event")
    member = await db.add_merit(1, -50, "manual", "overzealous officer")
    assert member.merit == 0
    entries = await db.history(1)
    assert sum(e.delta for e in entries) == 0, "log total must match the running total"


async def test_set_merit_records_a_correction(db):
    await db.add_merit(1, 10, "event")
    member = await db.set_merit(1, 42, officer_id=99, reason="migrated from spreadsheet")
    assert member.merit == 42
    latest = (await db.history(1))[0]
    assert latest.source == "correction"
    assert latest.delta == 32


async def test_once_cap(db):
    assert not await db.has_ever_logged(1, "oath")
    await db.add_merit(1, 2, "oath")
    assert await db.has_ever_logged(1, "oath")
    assert not await db.has_ever_logged(2, "oath")


async def test_once_cap_ignores_revocations(db):
    await db.add_merit(1, -2, "oath", "clerical error")
    assert not await db.has_ever_logged(1, "oath")


async def test_daily_cap(db):
    assert not await db.logged_today(1, "event")
    await db.add_merit(1, 5, "event")
    assert await db.logged_today(1, "event")
    assert not await db.logged_today(1, "operation")


async def test_weekly_window(db):
    await db.add_merit(1, 12, "tithe")
    await db.add_merit(1, 5, "tithe")
    assert await db.merit_from_source_since(1, "tithe", days=7) == 17
    assert await db.merit_from_source_since(1, "operation", days=7) == 0


async def test_flags(db):
    await db.set_flag(1, "oath", True)
    member = await db.get_member(1)
    assert member.oath and not member.uniform
    with pytest.raises(ValueError):
        await db.set_flag(1, "nonsense", True)


async def test_awards_are_unique_per_member(db):
    assert await db.add_award(1, "Iron Cross", "held the line", 99)
    assert not await db.add_award(1, "Iron Cross", None, 99)
    assert await db.add_award(2, "Iron Cross", None, 99)
    assert len(await db.awards(1)) == 1
    assert await db.remove_award(1, "Iron Cross")
    assert not await db.remove_award(1, "Iron Cross")


async def test_appointments_are_unique_per_member(db):
    assert await db.add_appointment(1, "governor", "Kaldun Province", 99)
    assert not await db.add_appointment(1, "governor", None, 99)
    records = await db.appointments(1)
    assert records[0].note == "Kaldun Province"
    assert await db.remove_appointment(1, "governor")


async def test_leaderboard_and_position(db):
    await db.add_merit(1, 50, "manual")
    await db.add_merit(2, 90, "manual")
    await db.add_merit(3, 10, "manual")
    board = await db.leaderboard(10)
    assert [m.user_id for m in board] == [2, 1, 3]
    assert await db.rank_position(2) == 1
    assert await db.rank_position(3) == 3
    assert await db.member_count() == 3
