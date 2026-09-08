"""Rank evaluation and role syncing.

Anything that moves a member's merit calls sync_rank afterwards. That keeps one
code path responsible for deciding a rank, swapping the roles and announcing
the result.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import discord

from .config import Config
from .db import Database, MemberRecord
from .ranks import RANK_BY_KEY, RANK_INDEX, TRACK_BASE, Rank, entitled_rank, get_track, is_gated

log = logging.getLogger(__name__)


@dataclass
class RankChange:
    old: Rank
    new: Rank
    gated: bool
    tracks: list[str] = field(default_factory=lambda: [TRACK_BASE])
    role_warning: str | None = None

    @property
    def track(self) -> str:
        """The ladder to quote when only one title fits."""
        return self.tracks[0] if self.tracks else TRACK_BASE

    @property
    def title(self) -> str:
        """What the new rank is called on the member's own ladder."""
        return get_track(self.track).title(self.new.key)

    @property
    def old_title(self) -> str:
        return get_track(self.track).title(self.old.key)

    @property
    def titles(self) -> str:
        """Every title this rank carries, for a member in more than one branch."""
        if len(self.tracks) < 2:
            return self.title
        return ", ".join(
            f"{get_track(t).title(self.new.key)} ({get_track(t).short})" for t in self.tracks
        )

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

    tracks = [TRACK_BASE]
    if member is not None:
        tracks = config.tracks_for({r.id for r in member.roles})

    change = RankChange(
        old=old,
        new=new,
        gated=is_gated(record.merit, record.oath, record.uniform),
        tracks=tracks,
    )

    if change.changed:
        await db.set_rank(record.user_id, new.key)

    if member is not None and config.manage_roles:
        change.role_warning = await apply_rank_roles(config, member, new, tracks)

    return change


PAUSED_NOTICE = "Role changes are paused, so merit is tracked but no roles move."


def paused_note(config: Config, change: RankChange) -> str | None:
    """Told to the officer when a rank moved but role syncing is switched off."""
    if config.manage_roles or not change.changed:
        return None
    return PAUSED_NOTICE


async def apply_rank_roles(
    config: Config, member: discord.Member, rank: Rank, tracks: list[str]
) -> str | None:
    """Give the member their rank role on every ladder they belong to.

    Members may sit in more than one branch, so this grants the rank on each of
    their ladders and one shared tier role. Ladder roles from branches they are
    not in get stripped, which is what makes a branch transfer clean itself up.
    """
    tier_id = config.tier_roles.get(rank.tier.value)
    wanted: list[tuple[int, str]] = []
    for track in tracks:
        role_id = config.rank_role(track, rank.key)
        if role_id is not None:
            wanted.append((role_id, get_track(track).title(rank.key)))
    if tier_id is not None:
        wanted.append((tier_id, rank.tier.value))

    keep = {role_id for role_id, _ in wanted}
    managed = config.all_rank_role_ids() | config.all_tier_role_ids()
    held = {r.id for r in member.roles}

    to_remove = [r for r in member.roles if r.id in managed and r.id not in keep]
    to_add = []
    missing: list[str] = []
    for role_id, label in wanted:
        if role_id in held:
            continue
        role = member.guild.get_role(role_id)
        if role is None:
            missing.append(f"{label} is configured as role {role_id} but that role does not exist")
            continue
        to_add.append(role)

    if not to_remove and not to_add:
        return "; ".join(missing) if missing else None

    try:
        if to_remove:
            await member.remove_roles(*to_remove, reason="Abexilian rank sync")
        if to_add:
            await member.add_roles(*to_add, reason="Abexilian rank sync")
    except discord.Forbidden:
        return (
            "I could not change roles. Give me Manage Roles and drag my role above the "
            "rank roles, Discord ignores Administrator for anything higher than my own role."
        )
    except discord.HTTPException as exc:
        log.warning("role sync failed for %s: %s", member.id, exc)
        return f"Discord rejected the role change: {exc}"
    return "; ".join(missing) if missing else None


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
        body = f"{member.mention} advances to {prefix}**{change.titles}**."
    else:
        title = "Rank adjustment"
        body = f"{member.mention} is now {prefix}**{change.titles}**, down from {change.old_title}."

    embed = discord.Embed(title=title, description=body, colour=config.embed_color)
    embed.set_footer(text=" and the ".join(get_track(t).label for t in change.tracks))
    try:
        await channel.send(embed=embed)
    except discord.HTTPException as exc:
        log.warning("could not announce rank change: %s", exc)
