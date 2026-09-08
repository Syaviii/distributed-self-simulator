"""Server specific configuration.

Role IDs, channel IDs and emoji change whenever the server is restructured, so
none of them live in source. Copy config.example.json to config.json and fill
it in once.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .ranks import APPOINTMENT_BY_KEY, RANK_BY_KEY

DEFAULT_PATH = Path("config.json")


class ConfigError(RuntimeError):
    pass


@dataclass
class Config:
    guild_id: int
    officer_roles: list[int] = field(default_factory=list)
    command_roles: list[int] = field(default_factory=list)
    rank_roles: dict[str, int] = field(default_factory=dict)
    appointment_roles: dict[str, int] = field(default_factory=dict)
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
            officer_roles=[int(v) for v in raw.get("officer_roles", []) if v],
            command_roles=[int(v) for v in raw.get("command_roles", []) if v],
            rank_roles={k: int(v) for k, v in raw.get("rank_roles", {}).items() if v},
            appointment_roles={k: int(v) for k, v in raw.get("appointment_roles", {}).items() if v},
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
        """Catch typos in rank and appointment keys at startup, not at 3am."""
        unknown_ranks = set(self.rank_roles) - set(RANK_BY_KEY)
        if unknown_ranks:
            raise ConfigError(f"rank_roles has unknown rank keys: {sorted(unknown_ranks)}")
        unknown_appointments = set(self.appointment_roles) - set(APPOINTMENT_BY_KEY)
        if unknown_appointments:
            raise ConfigError(
                f"appointment_roles has unknown appointment keys: {sorted(unknown_appointments)}"
            )
        if not self.officer_roles:
            raise ConfigError("officer_roles is empty, nobody would be able to log merit")

    def emoji(self, key: str) -> str:
        """Custom emoji for a rank or appointment, or an empty string if unset."""
        return self.emojis.get(key, "")

    def rank_role_ids(self) -> set[int]:
        return set(self.rank_roles.values())


def _optional_int(value: object) -> int | None:
    if value in (None, "", 0):
        return None
    return int(value)  # type: ignore[arg-type]
