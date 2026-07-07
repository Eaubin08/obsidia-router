"""Random dynamic batch tests."""

from app.router.decision import decide
from benchmarks.dynamic_cases_v2 import check_case_v2
from benchmarks.random_dynamic import generate_random_batches


def test_random_batches_are_replayable_with_seed():
    a = generate_random_batches(2, 12, base_seed=3108)
    b = generate_random_batches(2, 12, base_seed=3108)
    assert a == b


def test_random_batches_change_with_different_seed():
    a = generate_random_batches(2, 20, base_seed=3108)
    b = generate_random_batches(2, 20, base_seed=3109)
    a_requests = [c["request"] for batch in a["batches"] for c in batch["cases"]]
    b_requests = [c["request"] for batch in b["batches"] for c in batch["cases"]]
    assert a_requests != b_requests


def test_random_batches_hold_the_frame():
    plan = generate_random_batches(3, 25, base_seed=4108)
    failures = []

    for batch in plan["batches"]:
        for case in batch["cases"]:
            verdict = check_case_v2(case, decide(case["request"]))
            if not verdict["ok"]:
                failures.append(
                    f"batch={batch['batch_id']} seed={batch['seed']} "
                    f"{case['family']} | {case['request']} -> {verdict['failures']}"
                )

    assert not failures, "\n".join(failures)


def test_random_batch_seed_sequence_is_replay_friendly():
    plan = generate_random_batches(4, 5, base_seed=5000)
    assert [b["seed"] for b in plan["batches"]] == [5000, 5001, 5002, 5003]
