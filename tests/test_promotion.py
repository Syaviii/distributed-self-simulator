"""Rank syncing, with Discord left out of it."""

import pytest_asyncio

from abex.config import Config
from abex.db import Database
from abex.promotion import PAUSED_NOTICE, paused_note, sync_rank


def make_config(**overrides) -> Config:
    base = dict(guild_id=1, officer_roles=[10], command_roles=[11], manage_roles=False)
    base.update(overrides)
    return Config(**base)


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


async def test_promotion_is_recorded(db):
    config = make_config()
    record = await db.add_merit(1, 15, "manual")
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)
    record = await db.get_member(1)

    change = await sync_rank(config, db, record, None)
    assert change.promoted
    assert change.new.name == "Group Loyalist"
    assert (await db.get_member(1)).rank_key == "group_loyalist"


async def test_gate_stops_promotion_and_is_reported(db):
    config = make_config()
    record = await db.add_merit(1, 300, "manual")
    change = await sync_rank(config, db, record, None)
    assert change.new.name == "Group Loyalist"
    assert change.gated


async def test_clearing_the_gate_releases_the_backlog(db):
    config = make_config()
    record = await db.add_merit(1, 300, "manual")
    await sync_rank(config, db, record, None)

    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)
    change = await sync_rank(config, db, await db.get_member(1), None)
    assert change.new.name == "District Official"
    assert not change.gated


async def test_demotion_when_enabled(db):
    config = make_config(demote_on_merit_loss=True)
    await db.add_merit(1, 40, "manual")
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)
    await sync_rank(config, db, await db.get_member(1), None)

    await db.add_merit(1, -30, "manual", "stripped")
    change = await sync_rank(config, db, await db.get_member(1), None)
    assert change.changed and not change.promoted
    assert change.new.name == "Senior Loyalist"


async def test_rank_is_kept_when_demotion_is_disabled(db):
    config = make_config(demote_on_merit_loss=False)
    await db.add_merit(1, 40, "manual")
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)
    await sync_rank(config, db, await db.get_member(1), None)

    await db.add_merit(1, -40, "manual", "stripped")
    change = await sync_rank(config, db, await db.get_member(1), None)
    assert not change.changed
    assert change.new.name == "Unit Loyalist"


async def test_paused_config_never_touches_roles(db):
    """The backdating safeguard. Ranks still move, Discord roles do not."""
    config = make_config(manage_roles=False)
    await db.add_merit(1, 400, "manual")
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)

    # A member object that explodes if anything tries to change its roles.
    class Tripwire:
        roles: list = []

        async def add_roles(self, *args, **kwargs):
            raise AssertionError("role change attempted while paused")

        async def remove_roles(self, *args, **kwargs):
            raise AssertionError("role change attempted while paused")

    change = await sync_rank(config, db, await db.get_member(1), Tripwire())
    assert change.new.name == "Precinct Official"
    assert (await db.get_member(1)).rank_key == "precinct_official"
    assert paused_note(config, change) == PAUSED_NOTICE


async def test_paused_note_is_quiet_when_nothing_changed(db):
    config = make_config(manage_roles=False)
    change = await sync_rank(config, db, await db.ensure_member(1), None)
    assert not change.changed
    assert paused_note(config, change) is None


async def test_no_note_when_role_management_is_on(db):
    config = make_config(manage_roles=True)
    await db.add_merit(1, 10, "manual")
    change = await sync_rank(config, db, await db.get_member(1), None)
    assert change.changed
    assert paused_note(config, change) is None


def test_shipped_config_is_paused_for_backdating():
    """Flip this back on once existing merit totals are loaded."""
    assert Config.load("config.abexilian.json").manage_roles is False
