"""Entry point for the Abexilian Remnant merit and promotion bot."""

from __future__ import annotations

import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from abex.checks import MissingCommand, MissingOfficer
from abex.config import Config, ConfigError
from abex.db import Database

COGS = ("abex.cogs.merit", "abex.cogs.profile", "abex.cogs.roster")

log = logging.getLogger("abex")


class AbexBot(commands.Bot):
    def __init__(self, config: Config, db: Database) -> None:
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!abex ", intents=intents, help_command=None)
        self.config = config
        self.db = db

    async def setup_hook(self) -> None:
        await self.db.connect()
        for cog in COGS:
            await self.load_extension(cog)

        guild = discord.Object(id=self.config.guild_id)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        log.info("synced %d commands to guild %s", len(synced), self.config.guild_id)

    async def on_ready(self) -> None:
        log.info("connected as %s", self.user)
        await self.change_presence(activity=discord.Game(name="/profile"))

    async def close(self) -> None:
        await self.db.close()
        await super().close()


async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    if isinstance(error, (MissingOfficer, MissingCommand)):
        message = str(error) or "You are not allowed to do that."
    elif isinstance(error, app_commands.CommandOnCooldown):
        message = f"Slow down, try again in {error.retry_after:.0f}s."
    else:
        log.exception("command error", exc_info=error)
        message = "Something went wrong running that. The error has been logged."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    )

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")

    try:
        config = Config.load(os.getenv("CONFIG_PATH", "config.json"))
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    db = Database(os.getenv("DB_PATH", "data/abex.db"))
    bot = AbexBot(config, db)
    bot.tree.on_error = on_app_command_error

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
