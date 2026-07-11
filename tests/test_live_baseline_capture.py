"""Regression tests for raw-model baseline capture headroom."""

from pathlib import Path

from benchmarks.run_benchmark import (
    _BASELINE_CAPTURE_BUDGETS,
    _BASELINE_CAPTURE_POLICY,
    _baseline_capture_max_tokens,
)


def test_baseline_capture_policy_is_separate_and_named():
    assert _BASELINE_CAPTURE_POLICY == (
        "raw_model_capture_headroom_v1"
    )


def test_baseline_comparison_has_capture_headroom():
    prompt = (
        "Compare SQL and NoSQL databases and derive "
        "the main trade-offs."
    )

    assert _baseline_capture_max_tokens(prompt) == 850


def test_baseline_structured_summary_has_capture_headroom():
    prompt = (
        "Summarize the deployment plan in structured sections."
    )

    assert _baseline_capture_max_tokens(prompt) == 900


def test_baseline_code_has_capture_headroom():
    prompt = (
        "Implement a Python token bucket rate limiter with tests."
    )

    assert _baseline_capture_max_tokens(prompt) == 1700


def test_capture_budgets_do_not_equal_bounded_obsidia_budgets():
    assert _BASELINE_CAPTURE_BUDGETS["comparison"] == 850
    assert _BASELINE_CAPTURE_BUDGETS["code_file"] == 1700


def test_live_baseline_call_passes_explicit_max_tokens():
    import ast

    source = Path(
        "benchmarks/run_benchmark.py"
    ).read_text(encoding="utf-8")

    tree = ast.parse(source)

    def is_name(node, value):
        return (
            isinstance(node, ast.Name)
            and node.id == value
        )

    def is_task_request(node):
        return (
            isinstance(node, ast.Subscript)
            and is_name(node.value, "task")
            and isinstance(node.slice, ast.Constant)
            and node.slice.value == "request"
        )

    baseline_calls = []

    for candidate in ast.walk(tree):
        if not isinstance(candidate, ast.Call):
            continue

        func = candidate.func

        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "chat"
            and is_name(func.value, "fireworks")
        ):
            continue

        if len(candidate.args) < 2:
            continue

        if not is_name(candidate.args[0], "baseline_model"):
            continue

        if not is_task_request(candidate.args[1]):
            continue

        baseline_calls.append(candidate)

    assert len(baseline_calls) == 1

    keywords = {
        keyword.arg: keyword.value
        for keyword in baseline_calls[0].keywords
        if keyword.arg is not None
    }

    assert "max_tokens" in keywords
    assert is_name(
        keywords["max_tokens"],
        "_baseline_max_tokens",
    )

    budget_assignments = []

    for candidate in ast.walk(tree):
        if not isinstance(candidate, ast.Assign):
            continue

        if len(candidate.targets) != 1:
            continue

        target = candidate.targets[0]
        value = candidate.value

        if not is_name(target, "_baseline_max_tokens"):
            continue

        if not (
            isinstance(value, ast.Call)
            and is_name(
                value.func,
                "_baseline_capture_max_tokens",
            )
            and len(value.args) == 1
            and is_task_request(value.args[0])
        ):
            continue

        budget_assignments.append(candidate)

    assert len(budget_assignments) == 1


def test_quality_labels_distinguish_exact_and_accepted_routes():
    source = Path(
        "benchmarks/run_benchmark.py"
    ).read_text(encoding="utf-8")

    assert "Exact route match:" in source
    assert "Accepted route accuracy" in source
    assert (
        "Expected Fireworks route / actual remote calls:"
        in source
    )
