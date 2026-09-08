"""Server specific configuration.

Role IDs, channel IDs and emoji change whenever the server is restructured, so
none of them live in source. Copy config.example.json to config.json and fill
it in once.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .ranks import APPOINTMENT_BY_KEY, RANK_BY_KEY, TRACK_BASE, TRACKS, Tier

DEFAULT_PATH = Path("config.json")


class ConfigError(RuntimeError):
    pass


@dataclass
class Config:
    guild_id: int
    allowed_guilds: list[int] = field(default_factory=list)
    officer_roles: list[int] = field(default_factory=list)
    command_roles: list[int] = field(default_factory=list)
    rank_roles: dict[str, dict[str, int]] = field(default_factory=dict)
    appointment_roles: dict[str, dict[str, int]] = field(default_factory=dict)
    tier_roles: dict[str, int] = field(default_factory=dict)
    branch_tracks: dict[int, str] = field(default_factory=dict)
    emojis: dict[str, str] = field(default_factory=dict)
    promotion_channel: int | None = None
    audit_channel: int | None = None
    embed_color: int = 0xC9A227
    demote_on_merit_loss: bool = True
    manage_roles: bool = True

    @classmethod
    def load(cls, path: Path | str = DEFAULT_PATH) -> "Config":
        path = Path(path)
        if not path.exists():
            raise ConfigError(
                f"{path} not found. Copy config.example.json to {path} and fill in your IDs."
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        try:
            guild_id = int(raw["guild_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError("guild_id is missing or not a number") from exc

        cfg = cls(
            guild_id=guild_id,
            allowed_guilds=[int(v) for v in raw.get("allowed_guilds", []) if v],
            officer_roles=[int(v) for v in raw.get("officer_roles", []) if v],
            command_roles=[int(v) for v in raw.get("command_roles", []) if v],
            rank_roles=_role_map(raw.get("rank_roles", {})),
            appointment_roles=_role_map(raw.get("appointment_roles", {})),
            tier_roles={k: int(v) for k, v in raw.get("tier_roles", {}).items() if v},
            branch_tracks={int(k): str(v) for k, v in raw.get("branch_tracks", {}).items() if v},
            emojis={k: str(v) for k, v in raw.get("emojis", {}).items() if v},
            promotion_channel=_optional_int(raw.get("promotion_channel")),
            audit_channel=_optional_int(raw.get("audit_channel")),
            embed_color=int(str(raw.get("embed_color", "0xC9A227")), 0),
            demote_on_merit_loss=bool(raw.get("demote_on_merit_loss", True)),
            manage_roles=bool(raw.get("manage_roles", True)),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        """Catch typos in track, rank and appointment keys at startup, not at 3am."""
        for label, mapping, known in (
            ("rank_roles", self.rank_roles, set(RANK_BY_KEY)),
            ("appointment_roles", self.appointment_roles, set(APPOINTMENT_BY_KEY)),
        ):
            unknown_tracks = set(mapping) - set(TRACKS)
            if unknown_tracks:
                raise ConfigError(f"{label} has unknown tracks: {sorted(unknown_tracks)}")
            for track, entries in mapping.items():
                unknown = set(entries) - known
                if unknown:
                    raise ConfigError(f"{label}.{track} has unknown keys: {sorted(unknown)}")

        unknown_branch_tracks = set(self.branch_tracks.values()) - set(TRACKS)
        if unknown_branch_tracks:
            raise ConfigError(f"branch_tracks points at unknown tracks: {sorted(unknown_branch_tracks)}")

        unknown_tiers = set(self.tier_roles) - {t.value for t in Tier}
        if unknown_tiers:
            raise ConfigError(f"tier_roles has unknown tiers: {sorted(unknown_tiers)}")

        if not self.officer_roles:
            raise ConfigError("officer_roles is empty, nobody would be able to log merit")

        if self.guild_id not in self.guilds:
            raise ConfigError("allowed_guilds does not include guild_id")

    @property
    def guilds(self) -> set[int]:
        """Servers this bot will answer in. Anywhere else is ignored outright."""
        return {self.guild_id, *self.allowed_guilds}

    def is_allowed(self, guild_id: int | None) -> bool:
        return guild_id is not None and guild_id in self.guilds

    # role lookups ----------------------------------------------------------

    def tracks_for(self, role_ids: set[int]) -> list[str]:
        """Every ladder a member sits on, from their branch roles.

        Members may join all four branches at once, one division in each, so
        this returns a list rather than a single track. Someone in both the
        Commission and the Civil Service holds a rank on both ladders at the
        same merit total. Anyone with no branch role falls back to the base
        ranks, which the server calls the Bureaucracy structure.
        """
        found = {self.branch_tracks[r] for r in role_ids if r in self.branch_tracks}
        if not found:
            return [TRACK_BASE]
        return [t for t in TRACKS if t in found]

    def track_for(self, role_ids: set[int]) -> str:
        """The ladder to render titles from when only one can be shown."""
        return self.tracks_for(role_ids)[0]

    def rank_role(self, track: str, rank_key: str) -> int | None:
        """Role for a rank on a track, falling back to the base ladder."""
        return self.rank_roles.get(track, {}).get(rank_key) or self.rank_roles.get(
            TRACK_BASE, {}
        ).get(rank_key)

    def appointment_role(self, track: str, key: str) -> int | None:
        return self.appointment_roles.get(track, {}).get(key) or self.appointment_roles.get(
            TRACK_BASE, {}
        ).get(key)

    def all_rank_role_ids(self) -> set[int]:
        """Every ladder role across every track, so a transfer cleans up after itself."""
        return {role_id for entries in self.rank_roles.values() for role_id in entries.values()}

    def all_tier_role_ids(self) -> set[int]:
        return set(self.tier_roles.values())

    def emoji(self, key: str) -> str:
        """Custom emoji for a rank or appointment, or an empty string if unset."""
        return self.emojis.get(key, "")


def _role_map(raw: dict) -> dict[str, dict[str, int]]:
    """Read a track keyed map of role IDs, dropping anything left blank."""
    return {
        track: {key: int(value) for key, value in entries.items() if value}
        for track, entries in raw.items()
        if isinstance(entries, dict)
    }


def _optional_int(value: object) -> int | None:
    if value in (None, "", 0):
        return None
    return int(value)  # type: ignore[arg-type]
