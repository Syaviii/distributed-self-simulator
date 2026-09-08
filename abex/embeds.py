"""Embed builders. The profile card is the Abexilian ID card."""

from __future__ import annotations

from datetime import datetime

import discord

from .config import Config
from .db import AppointmentRecord, AwardRecord, LogEntry, MemberRecord
from .ranks import (
    APPOINTMENT_BY_KEY,
    RANK_BY_KEY,
    SOURCE_BY_KEY,
    Rank,
    is_gated,
    next_rank,
    rank_for_merit,
)

BAR_LENGTH = 12
BAR_FULL = "\N{FULL BLOCK}"
BAR_EMPTY = "\N{LIGHT SHADE}"

YES = "\N{WHITE HEAVY CHECK MARK}"
NO = "\N{CROSS MARK}"


def progress_bar(current: int, floor: int, ceiling: int) -> str:
    span = max(ceiling - floor, 1)
    done = max(0, min(BAR_LENGTH, round((current - floor) / span * BAR_LENGTH)))
    return BAR_FULL * done + BAR_EMPTY * (BAR_LENGTH - done)


def _timestamp(iso: str, style: str = "D") -> str:
    try:
        moment = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return f"<t:{int(moment.timestamp())}:{style}>"


def _titled(config: Config, key: str, name: str) -> str:
    emoji = config.emoji(key)
    return f"{emoji} {name}" if emoji else name


def profile_embed(
    config: Config,
    user: discord.Member | discord.User,
    record: MemberRecord,
    awards: list[AwardRecord],
    appointments: list[AppointmentRecord],
    position: int | None,
    population: int,
) -> discord.Embed:
    rank = RANK_BY_KEY.get(record.rank_key, RANK_BY_KEY["loyalist"])
    embed = discord.Embed(
        title=_titled(config, rank.key, rank.name),
        description=f"{rank.tier.value} of the Abexilian Remnant",
        colour=config.embed_color,
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.set_thumbnail(url=user.display_avatar.url)

    standing = f"**{record.merit}** merit"
    if position and population > 1:
        standing += f"\nRanked {position} of {population}"
    embed.add_field(name="Standing", value=standing, inline=True)

    embed.add_field(name="Progress", value=_progress_text(config, record, rank), inline=True)
    embed.add_field(name="Onboarding", value=_onboarding_text(record), inline=False)

    if appointments:
        embed.add_field(name="Appointments", value=_appointment_text(config, appointments), inline=False)
    if awards:
        embed.add_field(
            name=f"Awards ({len(awards)})",
            value="\n".join(f"{a.name}" + (f" - {a.note}" if a.note else "") for a in awards[:10]),
            inline=False,
        )

    embed.set_footer(text="Abexilian Remnant")
    embed.timestamp = discord.utils.utcnow()
    return embed


def _progress_text(config: Config, record: MemberRecord, rank: Rank) -> str:
    if is_gated(record.merit, record.oath, record.uniform):
        earned = rank_for_merit(record.merit)
        return (
            f"Held at {rank.name}.\n"
            f"Merit qualifies for **{earned.name}**, but the oath and uniform are required "
            "to advance past Group Loyalist."
        )

    upcoming = next_rank(rank)
    if upcoming is None:
        return f"{BAR_FULL * BAR_LENGTH}\nTop of the merit ladder. Further advancement is by appointment."

    bar = progress_bar(record.merit, rank.merit, upcoming.merit)
    remaining = upcoming.merit - record.merit
    return (
        f"{bar}\n{record.merit} / {upcoming.merit} merit\n"
        f"**{remaining}** to {_titled(config, upcoming.key, upcoming.name)}"
    )


def _onboarding_text(record: MemberRecord) -> str:
    return (
        f"{YES if record.oath else NO} Branch oath\n"
        f"{YES if record.uniform else NO} Division uniform"
    )


def _appointment_text(config: Config, appointments: list[AppointmentRecord]) -> str:
    lines = []
    for record in appointments:
        appointment = APPOINTMENT_BY_KEY.get(record.key)
        if appointment is None:
            continue
        line = f"{_titled(config, appointment.key, appointment.name)} ({appointment.group})"
        if record.note:
            line += f"\n> {record.note}"
        lines.append(line)
    return "\n".join(lines) if lines else "None recorded"


def history_embed(
    config: Config, user: discord.Member | discord.User, entries: list[LogEntry], total: int
) -> discord.Embed:
    embed = discord.Embed(
        title=f"Merit history for {user.display_name}",
        description=f"Current total: **{total}** merit",
        colour=config.embed_color,
    )
    if not entries:
        embed.add_field(name="Nothing logged yet", value="No merit has been recorded.", inline=False)
        return embed

    lines = []
    for entry in entries:
        source = SOURCE_BY_KEY.get(entry.source)
        label = source.label if source else entry.source.replace("_", " ").title()
        sign = "+" if entry.delta >= 0 else ""
        officer = f" by <@{entry.officer_id}>" if entry.officer_id else ""
        reason = f"\n> {entry.reason}" if entry.reason else ""
        lines.append(f"`{sign}{entry.delta:>4}` {label} {_timestamp(entry.created_at, 'R')}{officer}{reason}")

    embed.add_field(name="Recent entries", value="\n".join(lines)[:1024], inline=False)
    embed.set_footer(text="Newest first")
    return embed


def leaderboard_embed(
    config: Config, guild: discord.Guild, records: list[MemberRecord]
) -> discord.Embed:
    embed = discord.Embed(title="Merit standings", colour=config.embed_color)
    if not records:
        embed.description = "No merit has been logged yet."
        return embed

    lines = []
    for position, record in enumerate(records, start=1):
        rank = RANK_BY_KEY.get(record.rank_key, RANK_BY_KEY["loyalist"])
        emoji = config.emoji(rank.key)
        name = f"<@{record.user_id}>"
        lines.append(f"`{position:>2}.` {emoji} {name}  **{record.merit}** merit")

    embed.description = "\n".join(lines)
    embed.set_footer(text=f"{guild.name} - Abexilian Remnant")
    return embed
