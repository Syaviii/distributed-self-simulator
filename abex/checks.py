"""Permission checks.

Merit and appointment powers are granted by Discord role, listed in
config.json. Server owners and administrators always pass, so a fresh install
is never locked out of its own bot.
"""

from __future__ import annotations

import discord
from discord import app_commands


class MissingOfficer(app_commands.CheckFailure):
    message = "You need an officer role to do that."


class MissingCommand(app_commands.CheckFailure):
    message = "That is restricted to High Command."


def _has_any_role(member: discord.Member, role_ids: list[int]) -> bool:
    return any(role.id in role_ids for role in member.roles)


def _is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or member.id == member.guild.owner_id


def is_officer(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    config = interaction.client.config  # type: ignore[attr-defined]
    return (
        _is_admin(member)
        or _has_any_role(member, config.officer_roles)
        or _has_any_role(member, config.command_roles)
    )


def is_command_staff(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    config = interaction.client.config  # type: ignore[attr-defined]
    return _is_admin(member) or _has_any_role(member, config.command_roles)


def officer_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_officer(interaction):
            return True
        raise MissingOfficer(MissingOfficer.message)

    return app_commands.check(predicate)


def command_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_command_staff(interaction):
            return True
        raise MissingCommand(MissingCommand.message)

    return app_commands.check(predicate)
