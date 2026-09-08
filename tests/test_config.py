"""Config loading and validation."""

import json
from pathlib import Path

import pytest

from abex.config import Config, ConfigError


def make_config(**overrides) -> Config:
    base = dict(guild_id=1, officer_roles=[10], command_roles=[11], manage_roles=False)
    base.update(overrides)
    return Config(**base)


def test_config_rejects_unknown_rank_keys():
    with pytest.raises(ConfigError):
        make_config(rank_roles={"emperor_of_everything": 5}).validate()


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
