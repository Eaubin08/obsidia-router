"""Cognitive value inputs — the projection copies, it never computes.

Guards: whitelist of groups, no forbidden economic fields, values copied
verbatim (monotonicity by construction), boundary block always present.
"""
import copy
import json

from benchmarks.value_inputs import ALLOWED_GROUPS, cognitive_value_inputs


def _fake_report(**overrides) -> dict:
    report = {
        "route_accuracy": 1.0,
        "obsidia": {"fireworks_tokens": 1740, "estimated_tokens_saved": 4609,
                    "remote_calls_avoided": 15, "level0_rate": 0.61},
        "baseline_direct_model": {"tokens": 6939},
        "governance": {"governed_tasks": 8, "baseline_violations": 2,
                       "obsidia_violations": 0},
        "dynamic": {"invariants_held_rate": 1.0},
        "latency": {"avg_routing_ms_local": 0.07, "avg_fireworks_call_s": 0.9},
        "tasks": [{"gate": "ALLOW"}, {"gate": "HOLD"}, {"gate": "DENY"}],
    }
    for path, value in overrides.items():
        section, key = path.split(".")
        report[section][key] = value
    return report


def test_only_whitelisted_groups_are_emitted():
    cvi = cognitive_value_inputs(_fake_report())
    assert set(cvi.keys()) == ALLOWED_GROUPS


def test_no_forbidden_economic_fields():
    dump = json.dumps(cognitive_value_inputs(_fake_report())).lower()
    assert '"mint": true' not in dump
    assert '"wallet": true' not in dump
    assert '"blockchain": true' not in dump
    assert "token_price" not in dump
    assert '"economic_scoring": true' not in dump


def test_no_new_score_values_are_copied_verbatim():
    report = _fake_report()
    cvi = cognitive_value_inputs(report)
    assert cvi["avoided_inference"]["tokens_baseline"] == report["baseline_direct_model"]["tokens"]
    assert cvi["avoided_inference"]["estimated_tokens_saved"] == 4609
    assert cvi["frame_stability"]["baseline_violations"] == 2
    assert cvi["frame_stability"]["invariants_held_rate"] == 1.0
    assert cvi["control"]["route_accuracy"] == 1.0


def test_more_violations_are_reflected_not_hidden():
    low = cognitive_value_inputs(_fake_report())
    high = cognitive_value_inputs(_fake_report(**{"governance.baseline_violations": 7}))
    assert high["frame_stability"]["baseline_violations"] == 7
    assert high["frame_stability"]["baseline_violations"] > \
        low["frame_stability"]["baseline_violations"]


def test_improvements_are_reflected():
    base = cognitive_value_inputs(_fake_report())
    better = cognitive_value_inputs(_fake_report(
        **{"obsidia.remote_calls_avoided": 18, "obsidia.level0_rate": 0.8}))
    assert better["avoided_inference"]["remote_calls_avoided"] > \
        base["avoided_inference"]["remote_calls_avoided"]
    assert better["avoided_inference"]["level0_rate"] > \
        base["avoided_inference"]["level0_rate"]


def test_projection_does_not_mutate_the_report():
    report = _fake_report()
    snapshot = copy.deepcopy(report)
    cognitive_value_inputs(report)
    assert report == snapshot


def test_boundary_block_is_deferred_and_non_sovereign():
    bd = cognitive_value_inputs(_fake_report())["boundary"]
    assert bd["projection"] == "readonly"
    assert bd["decision_authority"] == "KX108_ONLY"
    assert "DEFERRED" in bd["status"]


def test_stdlib_only_no_private_imports():
    import benchmarks.value_inputs as vi
    source = open(vi.__file__, encoding="utf-8").read()
    assert "apps." not in source
    assert "periphery" not in source
    assert "import requests" not in source
