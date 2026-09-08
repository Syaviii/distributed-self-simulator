"""Appointments, awards and the oath and uniform flags."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..checks import command_only, officer_only
from ..promotion import PAUSED_NOTICE, announce, paused_note, sync_rank
from ..ranks import APPOINTMENT_BY_KEY, APPOINTMENTS, get_track

log = logging.getLogger(__name__)

APPOINTMENT_CHOICES = [
    app_commands.Choice(name=f"{a.name} ({a.group})", value=a.key) for a in APPOINTMENTS
][:25]


class Roster(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    group = app_commands.Group(name="roster", description="Appointments, awards and onboarding flags")

    # onboarding flags ------------------------------------------------------

    async def _set_flag(
        self, interaction: discord.Interaction, member: discord.Member, flag: str, value: bool, label: str
    ) -> None:
        await self.bot.db.set_flag(member.id, flag, value)
        record = await self.bot.db.ensure_member(member.id)
        change = await sync_rank(self.bot.config, self.bot.db, record, member)

        state = "recorded" if value else "cleared"
        lines = [f"{label} {state} for {member.mention}."]
        if change.changed:
            lines.append(f"They are now **{change.titles}**.")
        elif change.gated:
            lines.append(
                f"They are still held at {get_track(change.track).title('group_loyalist')} "
                "until both are recorded."
            )
        if change.role_warning:
            lines.append(f"Warning: {change.role_warning}")
        paused = paused_note(self.bot.config, change)
        if paused:
            lines.append(paused)

        await interaction.response.send_message("\n".join(lines))
        if change.changed and interaction.guild is not None:
            await announce(
                self.bot.config, interaction.guild, member, change, fallback=interaction.channel
            )

    @group.command(name="oath", description="Record or clear a member's branch oath")
    @app_commands.describe(member="Who took the oath", taken="Set false to clear it")
    @officer_only()
    async def oath(
        self, interaction: discord.Interaction, member: discord.Member, taken: bool = True
    ) -> None:
        await self._set_flag(interaction, member, "oath", taken, "Branch oath")

    @group.command(name="uniform", description="Record or clear a member's division uniform")
    @app_commands.describe(member="Who set their uniform", worn="Set false to clear it")
    @officer_only()
    async def uniform(
        self, interaction: discord.Interaction, member: discord.Member, worn: bool = True
    ) -> None:
        await self._set_flag(interaction, member, "uniform", worn, "Division uniform")

    # appointments ----------------------------------------------------------

    @group.command(name="appoint", description="Record an appointment")
    @app_commands.describe(member="Who is being appointed", appointment="Which title", note="Optional detail")
    @app_commands.choices(appointment=APPOINTMENT_CHOICES)
    @command_only()
    async def appoint(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        appointment: app_commands.Choice[str],
        note: str | None = None,
    ) -> None:
        title = APPOINTMENT_BY_KEY[appointment.value]
        added = await self.bot.db.add_appointment(member.id, title.key, note, interaction.user.id)
        if not added:
            await interaction.response.send_message(
                f"{member.display_name} already holds {title.name}.", ephemeral=True
            )
            return

        track = get_track(self.bot.config.track_for({r.id for r in member.roles}))
        warning = await self._apply_appointment_role(member, title.key, add=True)
        emoji = self.bot.config.emoji(title.key)
        prefix = f"{emoji} " if emoji else ""
        lines = [
            f"{member.mention} is appointed {prefix}**{track.title(title.key)}**, "
            f"{title.description}."
        ]
        if note:
            lines.append(f"> {note}")
        if warning:
            lines.append(f"Warning: {warning}")
        await interaction.response.send_message("\n".join(lines))

    @group.command(name="unappoint", description="Remove a recorded appointment")
    @app_commands.describe(member="Who is losing it", appointment="Which title")
    @app_commands.choices(appointment=APPOINTMENT_CHOICES)
    @command_only()
    async def unappoint(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        appointment: app_commands.Choice[str],
    ) -> None:
        title = APPOINTMENT_BY_KEY[appointment.value]
        removed = await self.bot.db.remove_appointment(member.id, title.key)
        if not removed:
            await interaction.response.send_message(
                f"{member.display_name} does not hold {title.name}.", ephemeral=True
            )
            return
        warning = await self._apply_appointment_role(member, title.key, add=False)
        text = f"{member.mention} no longer holds **{title.name}**."
        if warning:
            text += f"\nWarning: {warning}"
        await interaction.response.send_message(text)

    async def _apply_appointment_role(
        self, member: discord.Member, key: str, add: bool
    ) -> str | None:
        if not self.bot.config.manage_roles:
            return None
        track = self.bot.config.track_for({r.id for r in member.roles})
        role_id = self.bot.config.appointment_role(track, key)
        if role_id is None:
            return None
        role = member.guild.get_role(role_id)
        if role is None:
            return f"Appointment role {role_id} is configured but does not exist."
        try:
            if add:
                await member.add_roles(role, reason="Abexilian appointment")
            else:
                await member.remove_roles(role, reason="Abexilian appointment removed")
        except discord.Forbidden:
            return "I do not have permission to change that role."
        except discord.HTTPException as exc:
            log.warning("appointment role change failed: %s", exc)
            return f"Discord rejected the role change: {exc}"
        return None

    # awards ----------------------------------------------------------------

    @group.command(name="award", description="Grant an award")
    @app_commands.describe(member="Who receives it", name="Award name", note="Optional citation")
    @officer_only()
    async def award(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        name: app_commands.Range[str, 2, 80],
        note: app_commands.Range[str, 1, 200] | None = None,
    ) -> None:
        added = await self.bot.db.add_award(member.id, name, note, interaction.user.id)
        if not added:
            await interaction.response.send_message(
                f"{member.display_name} already holds the {name}.", ephemeral=True
            )
            return
        text = f"{member.mention} is awarded the **{name}**."
        if note:
            text += f"\n> {note}"
        await interaction.response.send_message(text)

    @group.command(name="unaward", description="Remove an award")
    @app_commands.describe(member="Who loses it", name="Exact award name")
    @officer_only()
    async def unaward(
        self, interaction: discord.Interaction, member: discord.Member, name: str
    ) -> None:
        removed = await self.bot.db.remove_award(member.id, name)
        if removed:
            await interaction.response.send_message(f"Removed the {name} from {member.mention}.")
        else:
            await interaction.response.send_message(
                f"{member.display_name} does not hold an award called {name}.", ephemeral=True
            )

    @unaward.autocomplete("name")
    async def award_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        member_id = _target_member_id(interaction)
        if member_id is None:
            return []
        awards = await self.bot.db.awards(member_id)
        current = current.lower()
        return [
            app_commands.Choice(name=a.name, value=a.name)
            for a in awards
            if current in a.name.lower()
        ][:25]

    # maintenance -----------------------------------------------------------

    @group.command(name="sync", description="Re-apply rank roles from stored merit")
    @app_commands.describe(member="Leave blank to sync everyone the bot knows about")
    @command_only()
    async def sync(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in the server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        if member is not None:
            targets = [member]
        else:
            records = await self.bot.db.leaderboard(limit=10000)
            targets = [m for m in (interaction.guild.get_member(r.user_id) for r in records) if m]

        changed = 0
        warnings: set[str] = set()
        for target in targets:
            record = await self.bot.db.ensure_member(target.id)
            result = await sync_rank(self.bot.config, self.bot.db, record, target)
            if result.changed:
                changed += 1
            if result.role_warning:
                warnings.add(result.role_warning)

        text = f"Synced {len(targets)} member(s). {changed} rank(s) changed."
        if not self.bot.config.manage_roles:
            text += f"\n{PAUSED_NOTICE}"
        if warnings:
            text += "\n" + "\n".join(f"Warning: {w}" for w in sorted(warnings))
        await interaction.followup.send(text, ephemeral=True)


def _target_member_id(interaction: discord.Interaction) -> int | None:
    """Pull the member option out of a partially filled command, for autocomplete."""
    data = interaction.data or {}
    for option in _walk_options(data.get("options", [])):
        if option.get("name") == "member":
            try:
                return int(option["value"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


def _walk_options(options: list[dict]) -> list[dict]:
    flat: list[dict] = []
    for option in options:
        if "options" in option:
            flat.extend(_walk_options(option["options"]))
        else:
            flat.append(option)
    return flat


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roster(bot))
