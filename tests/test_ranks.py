"""The ladder and the gate. Getting these wrong is invisible until someone complains."""

import pytest

from abex.ranks import (
    GATE_RANK_KEY,
    HIGHEST_RANK,
    RANKS,
    RANK_BY_KEY,
    entitled_rank,
    is_gated,
    merit_from_tithe,
    next_rank,
    rank_for_merit,
)


def test_thresholds_ascend():
    merits = [r.merit for r in RANKS]
    assert merits == sorted(merits)
    assert len(set(merits)) == len(merits)


@pytest.mark.parametrize(
    "merit,expected",
    [
        (0, "Loyalist"),
        (1, "Loyalist"),
        (2, "Junior Loyalist"),
        (9, "Junior Loyalist"),
        (10, "Senior Loyalist"),
        (15, "Group Loyalist"),
        (24, "Group Loyalist"),
        (25, "Section Loyalist"),
        (35, "Unit Loyalist"),
        (74, "Unit Loyalist"),
        (75, "Group Official"),
        (135, "Service Official"),
        (210, "Section Official"),
        (300, "District Official"),
        (400, "Precinct Official"),
        (10_000, "Precinct Official"),
    ],
)
def test_rank_for_merit(merit, expected):
    assert rank_for_merit(merit).name == expected


def test_gate_holds_at_group_loyalist():
    assert entitled_rank(400, oath=False, uniform=False).key == GATE_RANK_KEY
    assert entitled_rank(400, oath=True, uniform=False).key == GATE_RANK_KEY
    assert entitled_rank(400, oath=False, uniform=True).key == GATE_RANK_KEY
    assert entitled_rank(400, oath=True, uniform=True) is HIGHEST_RANK


def test_gate_does_not_block_below_itself():
    # Someone on 10 merit is nowhere near the gate, so it must not touch them.
    assert entitled_rank(10, oath=False, uniform=False).name == "Senior Loyalist"
    assert not is_gated(10, oath=False, uniform=False)


def test_is_gated_only_when_merit_would_promote():
    assert is_gated(25, oath=False, uniform=False)
    assert not is_gated(25, oath=True, uniform=True)
    assert not is_gated(15, oath=False, uniform=False)


def test_next_rank_runs_out_at_the_top():
    assert next_rank(RANK_BY_KEY["loyalist"]).name == "Junior Loyalist"
    assert next_rank(HIGHEST_RANK) is None


@pytest.mark.parametrize("amount,expected", [(0, 0), (999, 0), (1000, 1), (20_500, 20), (99_000, 99)])
def test_tithe_conversion(amount, expected):
    assert merit_from_tithe(amount) == expected
