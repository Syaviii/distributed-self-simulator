"""Rank evaluation and role syncing.

Anything that moves a member's merit calls sync_rank afterwards. That keeps one
code path responsible for deciding a rank, swapping the roles and announcing
the result.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from .config import Config
from .db import Database, MemberRecord
from .ranks import RANK_BY_KEY, RANK_INDEX, Rank, entitled_rank, is_gated

log = logging.getLogger(__name__)


@dataclass
class RankChange:
    old: Rank
    new: Rank
    gated: bool
    role_warning: str | None = None

    @property
    def changed(self) -> bool:
        return self.old.key != self.new.key

    @property
    def promoted(self) -> bool:
        return RANK_INDEX[self.new.key] > RANK_INDEX[self.old.key]


async def sync_rank(
    config: Config,
    db: Database,
    record: MemberRecord,
    member: discord.Member | None,
) -> RankChange:
    """Bring a member's stored rank and Discord roles in line with their merit."""
    old = RANK_BY_KEY.get(record.rank_key, RANK_BY_KEY["loyalist"])
    new = entitled_rank(record.merit, record.oath, record.uniform)

    if not config.demote_on_merit_loss and RANK_INDEX[new.key] < RANK_INDEX[old.key]:
        new = old

    change = RankChange(old=old, new=new, gated=is_gated(record.merit, record.oath, record.uniform))

    if change.changed:
        await db.set_rank(record.user_id, new.key)

    if member is not None and config.manage_roles:
        change.role_warning = await apply_rank_roles(config, member, new)

    return change


async def apply_rank_roles(config: Config, member: discord.Member, rank: Rank) -> str | None:
    """Give the member exactly one rank role. Returns a warning string on failure."""
    target_id = config.rank_roles.get(rank.key)
    managed = config.rank_role_ids()

    to_remove = [r for r in member.roles if r.id in managed and r.id != target_id]
    to_add = []
    if target_id is not None and target_id not in {r.id for r in member.roles}:
        role = member.guild.get_role(target_id)
        if role is None:
            return f"Rank role for {rank.name} is configured as {target_id} but does not exist."
        to_add.append(role)

    if not to_remove and not to_add:
        return None

    try:
        if to_remove:
            await member.remove_roles(*to_remove, reason="Abexilian rank sync")
        if to_add:
            await member.add_roles(*to_add, reason="Abexilian rank sync")
    except discord.Forbidden:
        return (
            "I could not change roles. Move my role above the rank roles and give me "
            "Manage Roles."
        )
    except discord.HTTPException as exc:
        log.warning("role sync failed for %s: %s", member.id, exc)
        return f"Discord rejected the role change: {exc}"
    return None


async def announce(
    config: Config,
    guild: discord.Guild,
    member: discord.Member | discord.User,
    change: RankChange,
    fallback: discord.abc.Messageable | None = None,
) -> None:
    """Post a promotion or demotion notice, if there is somewhere to post it."""
    if not change.changed:
        return

    channel: discord.abc.Messageable | None = None
    if config.promotion_channel is not None:
        found = guild.get_channel(config.promotion_channel)
        if isinstance(found, discord.abc.Messageable):
            channel = found
    if channel is None:
        channel = fallback
    if channel is None:
        return

    emoji = config.emoji(change.new.key)
    prefix = f"{emoji} " if emoji else ""
    if change.promoted:
        title = "Promotion"
        body = f"{member.mention} advances to {prefix}**{change.new.name}**."
    else:
        title = "Rank adjustment"
        body = f"{member.mention} is now {prefix}**{change.new.name}**, down from {change.old.name}."

    embed = discord.Embed(title=title, description=body, colour=config.embed_color)
    embed.set_footer(text=f"Previously {change.old.name}" if change.promoted else "Abexilian Remnant")
    try:
        await channel.send(embed=embed)
    except discord.HTTPException as exc:
        log.warning("could not announce rank change: %s", exc)
