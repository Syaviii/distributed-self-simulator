"""Merit logging, corrections and history."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..checks import command_only, officer_only
from ..db import MemberRecord
from ..embeds import history_embed, profile_embed
from ..promotion import RankChange, announce, paused_note, sync_rank
from ..ranks import (
    HOST_MIN_RANK_KEY,
    LOGGABLE_SOURCES,
    RANK_BY_KEY,
    RANK_INDEX,
    SOURCE_BY_KEY,
    TITHE_PER_MERIT,
    TITHE_SOURCE,
    TRACK_BASE,
    Cap,
    MeritSource,
    merit_from_tithe,
)

def _tracks_of(config, user) -> list[str]:
    """Every ladder this member promotes on, from their branch roles."""
    roles = getattr(user, "roles", None)
    return config.tracks_for({r.id for r in roles}) if roles else [TRACK_BASE]


SOURCE_CHOICES = [
    app_commands.Choice(name=f"{s.label} (+{s.merit})", value=s.key) for s in LOGGABLE_SOURCES
]


class Merit(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    group = app_commands.Group(name="merit", description="Log and adjust merit")

    # helpers ---------------------------------------------------------------

    async def _cap_refusal(self, user_id: int, source: MeritSource) -> str | None:
        """Why this grant is not allowed right now, or None if it is fine."""
        if source.cap is Cap.ONCE and await self.bot.db.has_ever_logged(user_id, source.key):
            return f"{source.label} is a one time award and has already been credited."
        if source.cap is Cap.DAILY and await self.bot.db.logged_today(user_id, source.key):
            return f"{source.label} has already been logged for them today. Try again tomorrow."
        return None

    async def _finish(
        self,
        interaction: discord.Interaction,
        member: discord.Member | discord.User,
        record: MemberRecord,
        headline: str,
    ) -> None:
        """Sync the rank, announce any change and reply with the result."""
        discord_member = member if isinstance(member, discord.Member) else None
        change: RankChange = await sync_rank(self.bot.config, self.bot.db, record, discord_member)

        lines = [headline, f"Total: **{record.merit}** merit, {change.title}."]
        if change.changed:
            verb = "Promoted to" if change.promoted else "Moved to"
            lines.append(f"{verb} **{change.titles}**.")
        if change.gated:
            lines.append(
                "Held at Group Loyalist until the oath and uniform are recorded. "
                "Use `/roster oath` and `/roster uniform`."
            )
        if change.role_warning:
            lines.append(f"Warning: {change.role_warning}")
        paused = paused_note(self.bot.config, change)
        if paused:
            lines.append(paused)

        await interaction.response.send_message("\n".join(lines))

        if change.changed and interaction.guild is not None:
            await announce(
                self.bot.config,
                interaction.guild,
                member,
                change,
                fallback=interaction.channel,
            )
        await self._audit(interaction, headline)

    async def _audit(self, interaction: discord.Interaction, text: str) -> None:
        channel_id = self.bot.config.audit_channel
        if channel_id is None or interaction.guild is None:
            return
        channel = interaction.guild.get_channel(channel_id)
        if isinstance(channel, discord.abc.Messageable):
            try:
                await channel.send(f"{text} (by {interaction.user.mention})")
            except discord.HTTPException:
                pass

    # commands --------------------------------------------------------------

    @group.command(name="check", description="Check your own merit standing")
    async def check(self, interaction: discord.Interaction) -> None:
        """The pinned guide tells members to run /merit, so this lives on the group."""
        user = interaction.user
        record = await self.bot.db.ensure_member(user.id)
        await interaction.response.send_message(
            embed=profile_embed(
                self.bot.config,
                user,
                record,
                await self.bot.db.awards(user.id),
                await self.bot.db.appointments(user.id),
                await self.bot.db.rank_position(user.id),
                await self.bot.db.member_count(),
                _tracks_of(self.bot.config, user),
            ),
            ephemeral=True,
        )

    @group.command(name="log", description="Credit merit from the standard activity table")
    @app_commands.describe(member="Who earned it", activity="What they did", note="Optional context")
    @app_commands.choices(activity=SOURCE_CHOICES)
    @officer_only()
    async def log(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        activity: app_commands.Choice[str],
        note: str | None = None,
    ) -> None:
        source = SOURCE_BY_KEY[activity.value]
        record = await self.bot.db.ensure_member(member.id)

        refusal = await self._cap_refusal(member.id, source)
        if refusal:
            await interaction.response.send_message(refusal, ephemeral=True)
            return

        if source.officers_only_subject:
            current = RANK_BY_KEY.get(record.rank_key)
            minimum = RANK_BY_KEY[HOST_MIN_RANK_KEY]
            if current is None or RANK_INDEX[current.key] < RANK_INDEX[minimum.key]:
                await interaction.response.send_message(
                    f"Hosting credit is for {minimum.name} and above. "
                    f"{member.display_name} is {record.rank_key.replace('_', ' ').title()}.",
                    ephemeral=True,
                )
                return

        # The oath and uniform are both a merit source and the gate on advancing
        # past Group Loyalist, so logging one flips the flag as well.
        if source.key in ("oath", "uniform"):
            await self.bot.db.set_flag(member.id, source.key, True)

        record = await self.bot.db.add_merit(
            member.id, source.merit, source.key, note, interaction.user.id
        )
        await self._finish(
            interaction, member, record, f"{member.mention} earned **+{source.merit}** for {source.label}."
        )

    @group.command(name="tithe", description="Credit merit for an Imperium tithe")
    @app_commands.describe(member="Who tithed", amount="Amount tithed, in currency or material value")
    @officer_only()
    async def tithe(
        self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1]
    ) -> None:
        earned = merit_from_tithe(amount)
        if earned == 0:
            await interaction.response.send_message(
                f"{amount} is under the {TITHE_PER_MERIT} needed for a single merit.", ephemeral=True
            )
            return

        already = await self.bot.db.merit_from_source_since(member.id, TITHE_SOURCE.key, days=7)
        remaining = TITHE_SOURCE.cap_value - already
        if remaining <= 0:
            await interaction.response.send_message(
                f"{member.display_name} has already hit the {TITHE_SOURCE.cap_value} merit tithe cap "
                "for this week.",
                ephemeral=True,
            )
            return

        granted = min(earned, remaining)
        record = await self.bot.db.add_merit(
            member.id, granted, TITHE_SOURCE.key, f"Tithed {amount}", interaction.user.id
        )

        headline = f"{member.mention} earned **+{granted}** for tithing {amount}."
        if granted < earned:
            headline += (
                f"\nCapped at the weekly limit. {earned - granted} merit was not credited "
                f"({TITHE_SOURCE.cap_value} per rolling week)."
            )
        await self._finish(interaction, member, record, headline)

    @group.command(name="grant", description="Grant merit outside the activity table")
    @app_commands.describe(member="Who to credit", amount="How much merit", reason="Why, required")
    @officer_only()
    async def grant(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 500],
        reason: str,
    ) -> None:
        record = await self.bot.db.add_merit(member.id, amount, "manual", reason, interaction.user.id)
        await self._finish(
            interaction, member, record, f"{member.mention} granted **+{amount}** merit. Reason: {reason}"
        )

    @group.command(name="revoke", description="Remove merit")
    @app_commands.describe(member="Who to debit", amount="How much merit", reason="Why, required")
    @officer_only()
    async def revoke(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 500],
        reason: str,
    ) -> None:
        before = await self.bot.db.ensure_member(member.id)
        record = await self.bot.db.add_merit(member.id, -amount, "manual", reason, interaction.user.id)
        taken = before.merit - record.merit
        headline = f"{member.mention} lost **{taken}** merit. Reason: {reason}"
        if taken < amount:
            headline += f"\nThey only had {before.merit}, so the balance stopped at zero."
        await self._finish(interaction, member, record, headline)

    @group.command(name="set", description="Force a merit total, recorded as a correction")
    @app_commands.describe(member="Who to correct", total="New merit total", reason="Why, required")
    @command_only()
    async def set_total(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        total: app_commands.Range[int, 0, 100000],
        reason: str,
    ) -> None:
        before = await self.bot.db.ensure_member(member.id)
        record = await self.bot.db.set_merit(member.id, total, interaction.user.id, reason)
        await self._finish(
            interaction,
            member,
            record,
            f"{member.mention} corrected from {before.merit} to **{record.merit}** merit. Reason: {reason}",
        )

    @group.command(name="history", description="Show a member's merit log")
    @app_commands.describe(member="Whose history to show", entries="How many entries, default 10")
    @officer_only()
    async def history(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        entries: app_commands.Range[int, 1, 25] = 10,
    ) -> None:
        record = await self.bot.db.ensure_member(member.id)
        log = await self.bot.db.history(member.id, entries)
        await interaction.response.send_message(
            embed=history_embed(self.bot.config, member, log, record.merit), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Merit(bot))
