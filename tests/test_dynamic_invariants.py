"""Dynamic bounded tests — the frame must hold on variations that were never
written down in advance.

The generator lives in benchmarks/dynamic_cases.py (single source, also run
by the benchmark's dynamic phase). Here every generated case must pass its
invariant verdict: correct route family, no model on level-0 families,
no-auto invariants always present, escalation only under ALLOW.
"""
from benchmarks.dynamic_cases import FAMILIES, check_case, generate_all
from app.router.decision import decide

N_PER_FAMILY = 25


def test_generated_cases_hold_the_frame():
    cases = generate_all(N_PER_FAMILY)
    assert len(cases) == N_PER_FAMILY * len(FAMILIES)
    failures = []
    for case in cases:
        verdict = check_case(case, decide(case["request"]))
        if not verdict["ok"]:
            failures.append(f"{case['family']} | {case['request']} -> {verdict['failures']}")
    assert not failures, "\n".join(failures)


def test_world_actions_never_reach_a_model():
    for case in generate_all(N_PER_FAMILY):
        if not case["level0_only"]:
            continue
        d = decide(case["request"])
        assert d["level"] == 0, case["request"]
        assert d["model"] is None, case["request"]


def test_generator_is_deterministic():
    assert generate_all(10) == generate_all(10)
