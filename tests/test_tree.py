"""Startup smoke test.

A name collision between a command and a group only shows up when the tree is
built, which on a live bot means at startup in front of everyone.
"""

import json

import pytest
import pytest_asyncio

from abex.config import Config
from abex.db import Database
from bot import COGS, AbexBot

pytestmark = pytest.mark.asyncio

EXPECTED = {
    "/leaderboard",
    "/profile",
    "/ranks",
    "/merit check",
    "/merit grant",
    "/merit history",
    "/merit log",
    "/merit revoke",
    "/merit set",
    "/merit tithe",
    "/roster appoint",
    "/roster award",
    "/roster oath",
    "/roster sync",
    "/roster unappoint",
    "/roster unaward",
    "/roster uniform",
}


@pytest_asyncio.fixture
async def bot(tmp_path):
    raw = json.loads(open("config.example.json").read())
    raw["guild_id"] = "1"
    raw["officer_roles"] = ["10"]
    raw["command_roles"] = ["11"]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw))

    instance = AbexBot(Config.load(path), Database(tmp_path / "test.db"))
    await instance.db.connect()
    for cog in COGS:
        await instance.load_extension(cog)
    yield instance
    await instance.db.close()


async def test_every_command_registers(bot):
    found = set()
    for command in bot.tree.get_commands():
        children = getattr(command, "commands", None)
        if children:
            found.update(f"/{command.name} {child.name}" for child in children)
        else:
            found.add(f"/{command.name}")
    assert found == EXPECTED


async def test_choices_stay_under_the_discord_limit(bot):
    from abex.cogs.merit import SOURCE_CHOICES
    from abex.cogs.roster import APPOINTMENT_CHOICES

    assert 0 < len(SOURCE_CHOICES) <= 25
    assert 0 < len(APPOINTMENT_CHOICES) <= 25
