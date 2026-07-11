"""Tests LOT G4 — model selection matrix (structure, graders, rankings).

No network: everything below is deterministic or mocked.
"""

from benchmarks.model_selection_matrix import (
    EVAL_MAX_TOKENS,
    EVAL_TIMEOUT_S,
    GRADER_LABEL,
    PRACTICE_GRADERS,
    best_single_model,
    category_winners,
    grade_answer,
    load_practice_tasks,
    model_metrics,
    rank_models,
)


def test_grader_label():
    assert GRADER_LABEL == "PRACTICE_DETERMINISTIC_GRADER"


def test_eight_graders_defined():
    assert len(PRACTICE_GRADERS) == 8
    cats = {c for _, c, _ in PRACTICE_GRADERS}
    assert cats == {
        "factual", "math_reasoning", "sentiment", "summarisation",
        "ner", "code_debugging", "logical_reasoning", "code_generation",
    }


def test_load_practice_tasks_maps_categories():
    tasks = load_practice_tasks()
    assert len(tasks) == 8
    assert all({"task_id", "category", "prompt"} <= set(t) for t in tasks)


def test_grade_factual_pass_and_fail():
    assert grade_answer("practice-01", "The capital is Canberra.")["pass"]
    assert not grade_answer("practice-01", "Sydney.")["pass"]


def test_grade_math_72():
    assert grade_answer("practice-02", "The average speed is 72 km/h.")["pass"]
    assert not grade_answer("practice-02", "It is 75 km/h.")["pass"]


def test_grade_code_debugging_rejects_unfixed():
    fixed = "def average(numbers):\n    return total / len(numbers)"
    buggy = "def average(numbers):\n    return total / len(numbers) + 1"
    assert grade_answer("practice-06", fixed)["pass"]
    assert not grade_answer("practice-06", buggy)["pass"]


def test_grade_dry_run_always_fails():
    g = grade_answer("practice-01", "[dry-run] canberra")
    assert not g["pass"]
    assert g["failure_reason"] == "dry_run_or_error_output"


def test_eval_bounds():
    assert EVAL_MAX_TOKENS == 8192
    assert EVAL_TIMEOUT_S == 60.0


def _row(model, task_id, cat, ok=True, tokens=100, lat=1.0,
         error=None, truncated=False):
    return {
        "model": model, "task_id": task_id, "category": cat,
        "grade": "PASS" if ok else "FAIL",
        "pass": ok, "format_compliant": ok, "truncated": truncated,
        "error": error, "transport_error_type": None,
        "prompt_tokens": tokens // 2, "completion_tokens": tokens // 2,
        "total_tokens": tokens, "latency_s": lat,
    }


def test_model_metrics_strict_8_of_8():
    rows = [_row("m1", f"p{i}", f"c{i}") for i in range(8)]
    m = model_metrics(rows, "m1")
    assert m["strict_8_of_8"] is True
    assert m["accuracy_rate"] == 1.0
    assert m["total_tokens"] == 800


def test_best_single_model_requires_clean_run():
    good = [_row("clean", f"p{i}", f"c{i}", tokens=200) for i in range(8)]
    cheap_but_failing = [
        _row("cheap", f"p{i}", f"c{i}", ok=(i != 0), tokens=50)
        for i in range(8)]
    metrics = [model_metrics(good, "clean"),
               model_metrics(cheap_but_failing, "cheap")]
    assert best_single_model(metrics) == "clean"


def test_best_single_model_none_when_no_pass():
    rows = [_row("m", f"p{i}", f"c{i}", ok=False) for i in range(8)]
    assert best_single_model([model_metrics(rows, "m")]) is None


def test_ranking_accuracy_before_tokens():
    accurate = [_row("acc", f"p{i}", f"c{i}", tokens=999) for i in range(8)]
    cheap = [_row("cheap", f"p{i}", f"c{i}", ok=(i < 4), tokens=1)
             for i in range(8)]
    ranked = rank_models([model_metrics(cheap, "cheap"),
                          model_metrics(accurate, "acc")])
    assert ranked[0]["model"] == "acc"


def test_category_winner_min_tokens_among_passing():
    rows = [
        _row("big", "p1", "factual", tokens=500),
        _row("small", "p1", "factual", tokens=100),
        _row("failing", "p1", "factual", ok=False, tokens=10),
    ]
    w = category_winners(rows)
    assert w["factual"]["winning_model"] == "small"


def test_category_winner_none_when_all_fail():
    rows = [_row("m", "p1", "factual", ok=False)]
    w = category_winners(rows)
    assert w["factual"]["winning_model"] is None
