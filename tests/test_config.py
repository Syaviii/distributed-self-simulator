"""Config loading and validation."""

import json
from pathlib import Path

import pytest

from abex.config import Config, ConfigError


def make_config(**overrides) -> Config:
    base = dict(guild_id=1, officer_roles=[10], command_roles=[11], manage_roles=False)
    base.update(overrides)
    return Config(**base)


def test_config_rejects_unknown_tracks():
    with pytest.raises(ConfigError):
        make_config(rank_roles={"imaginary_branch": {"loyalist": 5}}).validate()


def test_config_rejects_unknown_branch_tracks():
    with pytest.raises(ConfigError):
        make_config(branch_tracks={123: "not_a_track"}).validate()


def test_config_rejects_unknown_tiers():
    with pytest.raises(ConfigError):
        make_config(tier_roles={"Supreme Overlord": 5}).validate()


def test_config_rejects_unknown_rank_keys():
    with pytest.raises(ConfigError):
        make_config(rank_roles={"base": {"emperor_of_everything": 5}}).validate()


def test_config_rejects_an_empty_officer_list():
    with pytest.raises(ConfigError):
        make_config(officer_roles=[]).validate()


def test_example_config_matches_the_ladder(tmp_path):
    raw = json.loads(Path("config.example.json").read_text())
    raw["guild_id"] = "1"
    raw["officer_roles"] = ["10"]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw))
    config = Config.load(path)
    assert config.emoji("precinct_official").startswith("<:")


def test_shipped_abexilian_config_is_complete():
    """The config generated from the live server should need no hand editing."""
    from abex.ranks import RANKS, TRACK_BASE, TRACK_CIVIL, TRACK_COMPAO

    config = Config.load("config.abexilian.json")
    for track in (TRACK_BASE, TRACK_COMPAO, TRACK_CIVIL):
        for rank in RANKS:
            assert config.rank_role(track, rank.key), f"{track} is missing {rank.key}"
    assert len(config.all_rank_role_ids()) == len(RANKS) * 3, "tracks must not share roles"
    assert config.tier_roles, "tier roles are needed to keep the bureaucrat roles in step"


def test_tier_role_is_not_also_an_officer_role():
    """Otherwise reaching 75 merit would grant the power to log merit."""
    config = Config.load("config.abexilian.json")
    assert not set(config.tier_roles.values()) & set(config.officer_roles)
    assert not set(config.tier_roles.values()) & set(config.command_roles)
