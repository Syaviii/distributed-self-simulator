"""Embed rendering.

The profile card is the thing every member sees, so the failure that matters
here is it telling somebody the wrong rank.
"""

import types

import pytest
import pytest_asyncio

from abex.config import Config
from abex.db import Database
from abex.embeds import leaderboard_embed, profile_embed
from abex.ranks import TRACK_BASE, TRACK_CIVIL, TRACK_COMPAO


class FakeUser:
    def __init__(self, name="Tester", user_id=1):
        self.display_name = name
        self.id = user_id
        self.mention = f"<@{user_id}>"

    @property
    def display_avatar(self):
        return types.SimpleNamespace(url="https://example.invalid/a.png")


class FakeGuild:
    name = "Abexilian Remnant"


@pytest.fixture
def config():
    return Config.load("config.abexilian.json")


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(tmp_path / "e.db")
    await database.connect()
    yield database
    await database.close()


def fields(embed):
    return {f.name: f.value for f in embed.fields}


async def test_card_recomputes_the_rank_instead_of_trusting_the_stored_one(db, config):
    """A drifted rank_key, from an import or a manual edit, must not be believed."""
    await db.add_merit(1, 300, "manual")
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)
    await db.set_rank(1, "loyalist")  # deliberately wrong

    embed = profile_embed(config, FakeUser(), await db.get_member(1), [], [], 1, 1)
    assert "District Official" in embed.title


async def test_a_gated_member_is_shown_the_rank_the_gate_holds_them_at(db, config):
    await db.add_merit(1, 58, "manual")
    await db.set_flag(1, "oath", True)

    embed = profile_embed(config, FakeUser(), await db.get_member(1), [], [], 1, 1)
    assert "Group Loyalist" in embed.title
    progress = fields(embed)["Progress"]
    assert "Held at Group Loyalist" in progress
    assert "Unit Loyalist" in progress, "they should see what their merit already earned"
    assert "oath and uniform" in progress


async def test_onboarding_shows_what_is_still_missing(db, config):
    await db.set_flag(1, "oath", True)
    embed = profile_embed(config, FakeUser(), await db.get_member(1), [], [], 1, 1)
    onboarding = fields(embed)["Onboarding"]
    assert "\N{WHITE HEAVY CHECK MARK} Branch oath" in onboarding
    assert "\N{CROSS MARK} Division uniform" in onboarding


async def test_a_single_branch_member_gets_no_branches_field(db, config):
    await db.add_merit(1, 10, "manual")
    embed = profile_embed(config, FakeUser(), await db.get_member(1), [], [], 1, 1, [TRACK_BASE])
    assert "Branches" not in fields(embed)
    assert embed.description == "Junior Bureaucrat of the Abexilian Remnant"


async def test_a_dual_branch_member_is_named_on_both_ladders(db, config):
    await db.add_merit(1, 210, "manual")
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)

    embed = profile_embed(
        config, FakeUser(), await db.get_member(1), [], [], 1, 1, [TRACK_COMPAO, TRACK_CIVIL]
    )
    branches = fields(embed)["Branches"]
    assert "Commission: **Section Official**" in branches
    assert "Civil Service: **Supervisor**" in branches
    # The description must not pick one branch over the other.
    assert embed.description == "Senior Bureaucrat"


async def test_top_of_the_ladder_has_no_next_rank(db, config):
    await db.add_merit(1, 400, "manual")
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)
    embed = profile_embed(config, FakeUser(), await db.get_member(1), [], [], 1, 1)
    assert "appointment" in fields(embed)["Progress"]


async def test_leaderboard_shows_live_ranks_and_names_the_server_once(db, config):
    await db.add_merit(1, 238, "manual")
    await db.set_flag(1, "oath", True)
    await db.set_flag(1, "uniform", True)
    await db.add_merit(2, 5, "manual")
    await db.set_rank(1, "loyalist")  # stale

    embed = leaderboard_embed(config, FakeGuild(), await db.leaderboard(5))
    assert config.emoji("section_official") in embed.description
    assert embed.footer.text.count("Abexilian Remnant") == 1


def test_an_empty_leaderboard_says_so(config):
    embed = leaderboard_embed(config, FakeGuild(), [])
    assert "No merit" in embed.description
