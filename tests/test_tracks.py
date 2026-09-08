"""The three parallel ladders.

Every branch promotes on the same merit thresholds but holds different roles,
so the failure mode here is a member sitting on the right merit with the wrong
branch's role.
"""

import pytest
import pytest_asyncio

from abex.config import Config
from abex.db import Database
from abex.promotion import sync_rank
from abex.ranks import RANKS, TRACK_BASE, TRACK_CIVIL, TRACK_COMPAO, get_track

SELECT_COMMITTEE = 1462553332341276858
MINISTRY_OF_FINANCE = 1536306591677157436
ABEXILIAN_ARMY = 1536306406024683540


@pytest.fixture
def config():
    return Config.load("config.abexilian.json")


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


def test_branch_roles_pick_the_right_ladder(config):
    assert config.track_for({SELECT_COMMITTEE}) == TRACK_COMPAO
    assert config.track_for({MINISTRY_OF_FINANCE}) == TRACK_CIVIL
    assert config.track_for({ABEXILIAN_ARMY}) == TRACK_BASE
    assert config.track_for(set()) == TRACK_BASE


def test_civil_service_renames_the_whole_ladder():
    civil = get_track(TRACK_CIVIL)
    assert civil.title("loyalist") == "Intern"
    assert civil.title("section_official") == "Supervisor"
    assert civil.title("precinct_official") == "Chief Supervisor"
    assert civil.title("group_leader") == "President"


def test_compao_keeps_the_guide_titles():
    compao = get_track(TRACK_COMPAO)
    for rank in RANKS:
        assert compao.title(rank.key) == rank.name


def test_every_track_has_a_distinct_role_per_rank(config):
    for rank in RANKS:
        ids = {config.rank_role(t, rank.key) for t in (TRACK_BASE, TRACK_COMPAO, TRACK_CIVIL)}
        assert len(ids) == 3, f"{rank.key} reuses a role across tracks"


def test_appointments_fall_back_to_the_base_track(config):
    # The Civil Service has no Counselor of its own, so it borrows the base role.
    assert config.appointment_role(TRACK_CIVIL, "counselor") == config.appointment_role(
        TRACK_BASE, "counselor"
    )
    # But it does have its own name for the leader tiers.
    assert config.appointment_role(TRACK_CIVIL, "group_leader") != config.appointment_role(
        TRACK_BASE, "group_leader"
    )


def test_unknown_track_falls_back_to_base():
    assert get_track("nonsense").key == TRACK_BASE
    assert get_track(None).key == TRACK_BASE


async def test_rank_change_reports_the_members_own_title(db, config):
    await db.add_merit(1, 210, "manual")
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)
    change = await sync_rank(config, db, await db.get_member(1), None)

    assert change.new.name == "Section Official"
    change.track = TRACK_CIVIL
    assert change.title == "Supervisor"
    change.track = TRACK_COMPAO
    assert change.title == "Section Official"
