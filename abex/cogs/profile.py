"""Member facing commands. These are the ones the whole server will use."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..embeds import leaderboard_embed, profile_embed
from ..ranks import RANKS, Tier


class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="profile", description="Show an Abexilian ID card")
    @app_commands.describe(member="Whose card to show, defaults to your own")
    async def profile(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        target = member or interaction.user
        record = await self.bot.db.ensure_member(target.id)
        awards = await self.bot.db.awards(target.id)
        appointments = await self.bot.db.appointments(target.id)
        position = await self.bot.db.rank_position(target.id)
        population = await self.bot.db.member_count()

        await interaction.response.send_message(
            embed=profile_embed(
                self.bot.config, target, record, awards, appointments, position, population
            )
        )

    @app_commands.command(name="leaderboard", description="Top members by merit")
    @app_commands.describe(size="How many to list, default 10")
    async def leaderboard(
        self, interaction: discord.Interaction, size: app_commands.Range[int, 3, 25] = 10
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in the server.", ephemeral=True)
            return
        records = await self.bot.db.leaderboard(size)
        await interaction.response.send_message(
            embed=leaderboard_embed(self.bot.config, interaction.guild, records)
        )

    @app_commands.command(name="ranks", description="Show the merit ladder and its thresholds")
    async def ranks(self, interaction: discord.Interaction) -> None:
        config = self.bot.config
        embed = discord.Embed(
            title="Merit ladder",
            description="Ranks below are earned by merit. Everything above Precinct Official is "
            "conferred by appointment.",
            colour=config.embed_color,
        )
        for tier in (Tier.JUNIOR_BUREAUCRAT, Tier.SENIOR_BUREAUCRAT):
            lines = []
            for rank in reversed([r for r in RANKS if r.tier is tier]):
                emoji = config.emoji(rank.key)
                prefix = f"{emoji} " if emoji else ""
                lines.append(f"{prefix}**{rank.name}** at {rank.merit} merit")
            embed.add_field(name=tier.value, value="\n".join(lines), inline=False)

        embed.add_field(
            name="Gate",
            value="Group Loyalist needs the branch oath and a division uniform before anyone "
            "advances further, no matter how much merit they hold.",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))
