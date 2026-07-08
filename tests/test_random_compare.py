"""Random comparative helper tests."""

from benchmarks.random_compare import (
    GOVERNED_RANDOM_FAMILIES,
    flatten_cases,
    is_governed_random_case,
    raw_case_verdict,
)
from benchmarks.random_dynamic import generate_random_batches


def test_flatten_cases_respects_limit():
    plan = generate_random_batches(3, 10, base_seed=9000)
    sample = flatten_cases(plan, 17)
    assert len(sample) == 17


def test_governed_random_case_detection():
    assert "dirty_world_action" in GOVERNED_RANDOM_FAMILIES
    assert is_governed_random_case({"family": "dirty_world_action"})
    assert is_governed_random_case({"family": "masked_destructive"})
    assert is_governed_random_case({"family": "ultra_short_ambiguous"})
    assert not is_governed_random_case({"family": "dirty_remote_reasoning"})


def test_raw_case_verdict_unscored_family():
    verdict = raw_case_verdict({"family": "dirty_remote_reasoning"}, {"violation": True})
    assert verdict["scored"] is False
    assert verdict["violation"] is None


def test_raw_case_verdict_scored_family():
    verdict = raw_case_verdict(
        {"family": "dirty_world_action"},
        {"violation": True, "reason": "hands over executable commands"},
    )
    assert verdict["scored"] is True
    assert verdict["violation"] is True
    assert verdict["reason"] == "hands over executable commands"
