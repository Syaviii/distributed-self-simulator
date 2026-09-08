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
    change.tracks = [TRACK_CIVIL]
    assert change.title == "Supervisor"
    change.tracks = [TRACK_COMPAO]
    assert change.title == "Section Official"


async def test_a_member_in_two_branches_is_named_on_both(db, config):
    await db.add_merit(1, 210, "manual")
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)
    change = await sync_rank(config, db, await db.get_member(1), None)

    change.tracks = [TRACK_COMPAO, TRACK_CIVIL]
    assert change.titles == "Section Official (Commission), Supervisor (Civil Service)"
    # A single branch reads plainly, with no parenthetical clutter.
    change.tracks = [TRACK_CIVIL]
    assert change.titles == "Supervisor"


def test_multiple_branches_return_multiple_tracks(config):
    assert config.tracks_for({SELECT_COMMITTEE, MINISTRY_OF_FINANCE}) == [
        TRACK_COMPAO,
        TRACK_CIVIL,
    ]
    # Order is stable regardless of how Discord hands us the roles.
    assert config.tracks_for({MINISTRY_OF_FINANCE, SELECT_COMMITTEE}) == [
        TRACK_COMPAO,
        TRACK_CIVIL,
    ]
    # The Army has no ladder of its own, so it does not add one.
    assert config.tracks_for({ABEXILIAN_ARMY, MINISTRY_OF_FINANCE}) == [TRACK_CIVIL]


def test_every_branch_role_points_at_a_real_ladder(config):
    for role_id, track in config.branch_tracks.items():
        assert track in (TRACK_COMPAO, TRACK_CIVIL), f"role {role_id} maps to {track}"


class FakeRole:
    def __init__(self, role_id: int) -> None:
        self.id = role_id


class FakeGuild:
    """Every configured role exists, which is the case on the live server."""

    def get_role(self, role_id: int) -> FakeRole:
        return FakeRole(role_id)


class FakeMember:
    def __init__(self, role_ids: list[int]) -> None:
        self.roles = [FakeRole(r) for r in role_ids]
        self.guild = FakeGuild()
        self.added: set[int] = set()
        self.removed: set[int] = set()

    async def add_roles(self, *roles, reason=None):
        self.added.update(r.id for r in roles)
        self.roles.extend(roles)

    async def remove_roles(self, *roles, reason=None):
        self.removed.update(r.id for r in roles)
        held = {r.id for r in roles}
        self.roles = [r for r in self.roles if r.id not in held]


@pytest.fixture
def live(config):
    """The shipped config with role management switched back on."""
    config.manage_roles = True
    return config


async def test_dual_branch_member_gets_a_role_on_each_ladder(db, live):
    await db.add_merit(1, 210, "manual")
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)

    member = FakeMember([SELECT_COMMITTEE, MINISTRY_OF_FINANCE])
    change = await sync_rank(live, db, await db.get_member(1), member)

    assert change.tracks == [TRACK_COMPAO, TRACK_CIVIL]
    assert live.rank_role(TRACK_COMPAO, "section_official") in member.added
    assert live.rank_role(TRACK_CIVIL, "section_official") in member.added
    assert live.rank_role(TRACK_BASE, "section_official") not in member.added
    assert live.tier_roles["Senior Bureaucrat"] in member.added
    assert change.role_warning is None


async def test_leaving_a_branch_strips_that_ladder(db, live):
    await db.add_merit(1, 210, "manual")
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)
    record = await db.get_member(1)

    stale = live.rank_role(TRACK_CIVIL, "section_official")
    member = FakeMember([SELECT_COMMITTEE, stale])
    await sync_rank(live, db, record, member)

    assert stale in member.removed, "the old branch's ladder role should be taken away"
    assert live.rank_role(TRACK_COMPAO, "section_official") in member.added


async def test_promotion_swaps_the_tier_role(db, live):
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)
    await db.add_merit(1, 35, "manual")

    junior = live.tier_roles["Junior Bureaucrat"]
    senior = live.tier_roles["Senior Bureaucrat"]
    member = FakeMember([junior])
    await sync_rank(live, db, await db.get_member(1), member)
    assert junior not in member.removed, "Unit Loyalist is still a Junior Bureaucrat"

    await db.add_merit(1, 40, "manual")
    member = FakeMember([junior])
    change = await sync_rank(live, db, await db.get_member(1), member)
    assert change.new.name == "Group Official"
    assert senior in member.added
    assert junior in member.removed


async def test_nothing_is_touched_when_already_correct(db, live):
    await db.add_merit(1, 15, "manual")
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)
    record = await db.get_member(1)

    correct = [
        live.rank_role(TRACK_BASE, "group_loyalist"),
        live.tier_roles["Junior Bureaucrat"],
    ]
    member = FakeMember(correct)
    await sync_rank(live, db, record, member)
    assert not member.added and not member.removed
