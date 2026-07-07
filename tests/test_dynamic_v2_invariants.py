"""Dynamic V2 dirty invariant tests."""

from benchmarks.dynamic_cases_v2 import FAMILIES_V2, check_case_v2, generate_all_v2
from app.router.decision import decide

N_PER_FAMILY = 15


def test_dirty_generated_cases_hold_the_frame():
    cases = generate_all_v2(N_PER_FAMILY)
    assert len(cases) == N_PER_FAMILY * len(FAMILIES_V2)

    failures = []
    for case in cases:
        verdict = check_case_v2(case, decide(case["request"]))
        if not verdict["ok"]:
            failures.append(
                f"{case['family']} | {case['request']} -> {verdict['failures']}"
            )

    assert not failures, "\n".join(failures)


def test_dirty_level0_families_never_reach_model():
    for case in generate_all_v2(N_PER_FAMILY):
        if not case["level0_only"]:
            continue
        d = decide(case["request"])
        assert d["level"] == 0, case["request"]
        assert d["model"] is None, case["request"]


def test_dirty_generator_is_deterministic():
    assert generate_all_v2(10) == generate_all_v2(10)


def test_brody_identity_edge_never_reaches_remote_model():
    for case in generate_all_v2(N_PER_FAMILY):
        if case["family"] != "brody_identity_edge":
            continue
        d = decide(case["request"])
        assert d["route"] in {"brody", "clarification_needed"}
        assert d["level"] <= 1
        assert d["model"] is None
