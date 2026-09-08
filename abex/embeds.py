"""Embed builders. The profile card is the Abexilian ID card."""

from __future__ import annotations

from datetime import datetime

import discord

from .config import Config
from .db import AppointmentRecord, AwardRecord, LogEntry, MemberRecord
from .ranks import (
    APPOINTMENT_BY_KEY,
    SOURCE_BY_KEY,
    TRACK_BASE,
    Rank,
    Track,
    entitled_rank,
    get_track,
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


def _ranked(config: Config, track: Track, key: str) -> str:
    """A rank or appointment rendered with the title used on that ladder."""
    return _titled(config, key, track.title(key))


def profile_embed(
    config: Config,
    user: discord.Member | discord.User,
    record: MemberRecord,
    awards: list[AwardRecord],
    appointments: list[AppointmentRecord],
    position: int | None,
    population: int,
    track_keys: list[str] | None = None,
) -> discord.Embed:
    tracks = [get_track(k) for k in (track_keys or [TRACK_BASE])]
    track = tracks[0]
    rank = entitled_rank(record.merit, record.oath, record.uniform)
    # Multi branch members are named on each ladder in the Branches field, so
    # the description does not pick a favourite.
    home = f"{rank.tier.value} of the {track.label}" if len(tracks) == 1 else rank.tier.value
    embed = discord.Embed(
        title=_ranked(config, track, rank.key),
        description=home,
        colour=config.embed_color,
    )
    embed.set_author(name=user.display_name)
    embed.set_thumbnail(url=user.display_avatar.url)

    standing = f"**{record.merit}** merit"
    if position and population > 1:
        standing += f"\nRanked {position} of {population}"
    embed.add_field(name="Standing", value=standing, inline=True)

    embed.add_field(name="Progress", value=_progress_text(config, record, rank, track), inline=True)
    embed.add_field(name="Onboarding", value=_onboarding_text(record), inline=False)

    if len(tracks) > 1:
        # A member in more than one branch holds a rank on each ladder.
        embed.add_field(
            name="Branches",
            value="\n".join(f"{t.short}: **{t.title(rank.key)}**" for t in tracks),
            inline=False,
        )

    if appointments:
        embed.add_field(
            name="Appointments", value=_appointment_text(config, track, appointments), inline=False
        )
    if awards:
        embed.add_field(
            name=f"Awards ({len(awards)})",
            value="\n".join(f"{a.name}" + (f" - {a.note}" if a.note else "") for a in awards[:10]),
            inline=False,
        )

    embed.set_footer(text="Abexilian Remnant")
    embed.timestamp = discord.utils.utcnow()
    return embed


def _progress_text(config: Config, record: MemberRecord, rank: Rank, track: Track) -> str:
    if is_gated(record.merit, record.oath, record.uniform):
        earned = rank_for_merit(record.merit)
        return (
            f"Held at {track.title(rank.key)}.\n"
            f"Merit qualifies for **{track.title(earned.key)}**, but the oath and uniform "
            "are required to advance further."
        )

    upcoming = next_rank(rank)
    if upcoming is None:
        return f"{BAR_FULL * BAR_LENGTH}\nTop of the merit ladder. Further advancement is by appointment."

    bar = progress_bar(record.merit, rank.merit, upcoming.merit)
    remaining = upcoming.merit - record.merit
    return (
        f"{bar}\n{record.merit} / {upcoming.merit} merit\n"
        f"**{remaining}** to {_ranked(config, track, upcoming.key)}"
    )


def _onboarding_text(record: MemberRecord) -> str:
    return (
        f"{YES if record.oath else NO} Branch oath\n"
        f"{YES if record.uniform else NO} Division uniform"
    )


def _appointment_text(
    config: Config, track: Track, appointments: list[AppointmentRecord]
) -> str:
    lines = []
    for record in appointments:
        appointment = APPOINTMENT_BY_KEY.get(record.key)
        if appointment is None:
            continue
        line = f"{_ranked(config, track, appointment.key)} ({appointment.group})"
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
        rank = entitled_rank(record.merit, record.oath, record.uniform)
        emoji = config.emoji(rank.key)
        name = f"<@{record.user_id}>"
        lines.append(f"`{position:>2}.` {emoji} {name}  **{record.merit}** merit")

    embed.description = "\n".join(lines)
    embed.set_footer(text=f"{guild.name} merit ladder")
    return embed
