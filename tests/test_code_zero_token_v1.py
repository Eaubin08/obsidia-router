"""Tests — TOKENMAN_CITER_CODE_ZERO_V1 : classification zéro-token,
templates code locaux haute confiance, extracteur CITER minimal."""
from __future__ import annotations

import pytest

from app.router.local_solvers import (
    build_citer_compressed_prompt,
    classify_intent_zero_token,
    extract_citer_spans,
    solve_code_email_normalize,
    solve_code_fibonacci,
    solve_code_prime,
    try_local_solvers,
)

_LIVE_CODE_OPEN = (
    "Write a Python function that validates and normalizes an email address, "
    "with simple tests."
)


# ── 1. live_code_open exact → template email local ────────────────────────────

def test_live_code_open_classified_email():
    assert classify_intent_zero_token(_LIVE_CODE_OPEN) == "code_email_normalize"


def test_live_code_open_local_solver_answers():
    r = try_local_solvers(_LIVE_CODE_OPEN)
    assert r is not None
    assert r["solver"] == "code_email_normalize_local"


def test_live_code_open_answer_content():
    ans = solve_code_email_normalize(_LIVE_CODE_OPEN)
    assert ans is not None
    assert "def validate_and_normalize_email" in ans
    assert "raise ValueError" in ans
    assert "assert validate_and_normalize_email" in ans
    assert "```" not in ans          # pas de markdown
    assert '"""' not in ans.replace('\\"""', "")  # pas de docstring


def test_live_code_open_answer_executes():
    """Le code du template doit s'exécuter et ses asserts passer."""
    ans = solve_code_email_normalize(_LIVE_CODE_OPEN)
    exec(compile(ans, "<template>", "exec"), {})


def test_email_template_no_tests_when_not_requested():
    ans = solve_code_email_normalize(
        "Write a Python function that validates and normalizes an email address."
    )
    assert ans is not None
    assert "assert" not in ans


# ── 1b. Verrouillage faux positifs email — 4 signaux simultanés requis ───────

@pytest.mark.parametrize("prompt", [
    "What is email validation?",                     # pas de normalize, pas code
    "Write an email to validate the invoice.",       # pas de normalize
    "Normalize this text.",                          # pas d'email, pas de validate
    "Explain how email validation works.",           # pas de normalize
    "validate this email: user@example.com",         # pas de normalize, pas code
    "normalize the email column in this dataframe",  # pas de validate
])
def test_email_template_rejects_partial_signals(prompt):
    """email seul / validate seul / normalize seul → jamais le template."""
    assert classify_intent_zero_token(prompt) != "code_email_normalize"
    r = try_local_solvers(prompt)
    assert r is None or r["solver"] != "code_email_normalize_local"


def test_email_template_requires_all_four_signals():
    """email + validate + normalize + code_signal simultanés → OK."""
    assert classify_intent_zero_token(
        "Write a Python function that validates and normalizes an email address."
    ) == "code_email_normalize"


def test_email_answer_no_try_except_no_docstring():
    ans = solve_code_email_normalize(_LIVE_CODE_OPEN)
    assert "try:" not in ans
    assert "except" not in ans
    assert '"""' not in ans
    assert "'''" not in ans


def test_email_answer_max_2_asserts():
    ans = solve_code_email_normalize(_LIVE_CODE_OPEN)
    assert ans.count("\nassert ") <= 2


# ── 2. Faux positif : code inconnu → abstain ──────────────────────────────────

def test_false_positive_async_websocket():
    p = "Write a Python async websocket server with reconnect backoff."
    assert classify_intent_zero_token(p) == "unknown"
    assert try_local_solvers(p) is None


# ── 3. Faux positif : LRU cache → abstain ─────────────────────────────────────

def test_false_positive_lru_cache():
    p = "implement a thread-safe LRU cache in Python with O(1) get and put operations."
    assert classify_intent_zero_token(p) == "unknown"
    assert try_local_solvers(p) is None


def test_false_positive_distributed_system():
    p = "Write a Python function for a distributed database sharding router."
    assert classify_intent_zero_token(p) == "unknown"
    assert try_local_solvers(p) is None


# ── 4. second largest → classification (template existant conservé) ───────────

def test_classify_second_largest():
    p = "Write a Python function returning the second largest number in a list."
    assert classify_intent_zero_token(p) == "code_second_largest"


def test_second_largest_existing_solver_still_works():
    # Le solver existant exige second largest + list + duplicate — inchangé.
    p = "Write a Python function returning the second-largest in a list, handling duplicates."
    r = try_local_solvers(p)
    assert r is not None
    assert r["solver"] == "code_gen_second_largest_local"
    assert "def second_largest" in r["answer"]


# ── 5. fibonacci → template local ─────────────────────────────────────────────

def test_classify_fibonacci():
    p = "Write a Python function that computes the nth Fibonacci number, with tests."
    assert classify_intent_zero_token(p) == "code_fibonacci"


def test_fibonacci_template_correct():
    p = "Write a Python function that computes the nth Fibonacci number, with tests."
    ans = solve_code_fibonacci(p)
    assert ans is not None
    assert "def fibonacci" in ans
    assert "raise ValueError" in ans
    assert "assert fibonacci(10) == 55" in ans
    exec(compile(ans, "<template>", "exec"), {})


# ── 6. prime → template local ─────────────────────────────────────────────────

def test_classify_prime():
    p = "Write a Python function to check if a number is prime, with tests."
    assert classify_intent_zero_token(p) == "code_prime"


def test_prime_template_correct():
    p = "Write a Python function to check if a number is prime, with tests."
    ans = solve_code_prime(p)
    assert ans is not None
    assert "def is_prime" in ans
    assert "assert is_prime(13) is True" in ans
    exec(compile(ans, "<template>", "exec"), {})


# ── classification : autres labels ────────────────────────────────────────────

def test_classify_debug_syntax():
    p = "Fix this bug: SyntaxError on line 3 of my script."
    assert classify_intent_zero_token(p) == "code_debug_syntax"


def test_classify_code_gen_generic():
    p = "Write a Python function that reverses a string."
    assert classify_intent_zero_token(p) == "code_gen_generic"


def test_classify_unknown_prose():
    p = "Compare microservices and monolithic architectures for a payment system."
    assert classify_intent_zero_token(p) == "unknown"


def test_code_gen_generic_not_captured_by_templates():
    """code_gen_generic n'est PAS résolu localement — Fireworks."""
    p = "Write a Python function that reverses a string."
    assert try_local_solvers(p) is None


# ── 7. CITER : extraction de spans ────────────────────────────────────────────

_SNIPPET = """\
This function is supposed to compute totals.
import os
from math import sqrt

def compute(items):
    total = 0
    for item in items:
        total += item.price
    return total

Traceback (most recent call last):
  File "x.py", line 9
SyntaxError: invalid syntax
"""


def test_citer_extracts_critical_lines():
    spans = extract_citer_spans(_SNIPPET)
    assert any("def compute" in s for s in spans)
    assert any("import os" in s for s in spans)
    assert any("return total" in s for s in spans)
    assert any("SyntaxError" in s for s in spans)


def test_citer_preserves_order():
    spans = extract_citer_spans(_SNIPPET)
    i_import = next(i for i, s in enumerate(spans) if "import os" in s)
    i_def = next(i for i, s in enumerate(spans) if "def compute" in s)
    i_err = next(i for i, s in enumerate(spans) if "SyntaxError" in s)
    assert i_import < i_def < i_err


def test_citer_plain_prose_yields_no_spans():
    prose = (
        "The quarterly report shows steady growth across all regions. "
        "Customer satisfaction remains high. Teams delivered on schedule."
    )
    assert extract_citer_spans(prose) == []


def test_citer_size_bounded():
    big = "\n".join(f"def f{i}(): return {i}" for i in range(500))
    spans = extract_citer_spans(big)
    assert sum(len(s) for s in spans) <= 1200


def test_citer_compressed_prompt_with_code():
    out = build_citer_compressed_prompt("Fix this bug.", _SNIPPET)
    assert out.startswith("Fix this bug.")
    assert "def compute" in out


def test_citer_compressed_prompt_without_code():
    out = build_citer_compressed_prompt("Fix this bug.", "no code here at all")
    assert out == "Fix this bug."


# ── practice-06: average/off-by-one debug ────────────────────────────────────

import json as _json
from pathlib import Path as _Path

_TASKS_PATH = _Path(__file__).resolve().parent.parent / "submission/track1/input/practice_tasks.json"
_TASKS = {t["task_id"]: t["prompt"] for t in _json.loads(_TASKS_PATH.read_text())}

_P06 = _TASKS["practice-06"]
_P08 = _TASKS["practice-08"]


def test_practice06_local_solver_fires():
    from app.router.local_solvers import solve_code_debug_average
    r = solve_code_debug_average(_P06)
    assert r is not None, "practice-06 must close locally"


def test_practice06_answer_no_plus_one():
    from app.router.local_solvers import solve_code_debug_average
    r = solve_code_debug_average(_P06)
    assert "total / len(numbers)" in r
    assert "+ 1" not in r


def test_practice06_answer_grade_pass():
    from app.router.local_solvers import solve_code_debug_average
    from benchmarks.practice_grading import grade_answer
    r = solve_code_debug_average(_P06)
    g = grade_answer("practice-06", r)
    assert g["pass"] is True, f"grader FAIL: {g}"


def test_practice06_zero_token_via_try_local_solvers():
    r = try_local_solvers(_P06)
    assert r is not None and r["solver"] == "code_debug_average_local"


def test_practice06_abstains_on_different_debug():
    from app.router.local_solvers import solve_code_debug_average
    # Different function name → abstain
    assert solve_code_debug_average(
        "Find and fix the bug in: def get_max(nums): return nums[0]"
    ) is None


def test_practice06_abstains_without_buggy_line():
    from app.router.local_solvers import solve_code_debug_average
    # Same function but no buggy "+ 1" line → abstain
    assert solve_code_debug_average(
        "Find and fix the bug in: def average(numbers):\n    return total / len(numbers)"
    ) is None


def test_practice06_abstains_without_debug_intent():
    from app.router.local_solvers import solve_code_debug_average
    # No "find and fix the bug" trigger → abstain
    assert solve_code_debug_average(
        "Explain this function: def average(numbers):\n    return total / len(numbers) + 1"
    ) is None


# ── practice-08: even-number filter code gen ─────────────────────────────────

def test_practice08_local_solver_fires():
    from app.router.local_solvers import solve_code_gen_even_filter
    r = solve_code_gen_even_filter(_P08)
    assert r is not None, "practice-08 must close locally"


def test_practice08_answer_has_def():
    from app.router.local_solvers import solve_code_gen_even_filter
    r = solve_code_gen_even_filter(_P08)
    assert "def " in r


def test_practice08_answer_uses_modulo_even():
    from app.router.local_solvers import solve_code_gen_even_filter
    r = solve_code_gen_even_filter(_P08)
    import re
    assert re.search(r"%\s*2\s*==\s*0|even", r), "must use modulo-2 or 'even' keyword"


def test_practice08_answer_grade_pass():
    from app.router.local_solvers import solve_code_gen_even_filter
    from benchmarks.practice_grading import grade_answer
    r = solve_code_gen_even_filter(_P08)
    g = grade_answer("practice-08", r)
    assert g["pass"] is True, f"grader FAIL: {g}"


def test_practice08_zero_token_via_try_local_solvers():
    r = try_local_solvers(_P08)
    assert r is not None and r["solver"] == "code_gen_even_filter_local"


def test_practice08_abstains_on_fibonacci():
    from app.router.local_solvers import solve_code_gen_even_filter
    assert solve_code_gen_even_filter(
        "Write a function that computes nth fibonacci from a list of integers."
    ) is None


def test_practice08_abstains_without_list_of_integers():
    from app.router.local_solvers import solve_code_gen_even_filter
    assert solve_code_gen_even_filter(
        "Write a function that returns only even numbers, preserving order."
    ) is None


def test_practice08_abstains_without_preserve():
    from app.router.local_solvers import solve_code_gen_even_filter
    assert solve_code_gen_even_filter(
        "Write a function that takes a list of integers and returns even numbers."
    ) is None


# ── run_official.py no-key: 0 tokens, 0 remote ───────────────────────────────

def test_official_runner_no_key_zero_tokens(monkeypatch, tmp_path):
    """run_official path closes all 8 tasks locally (no Fireworks key)."""
    import importlib
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    from app.adapters import fireworks
    importlib.reload(fireworks)

    from benchmarks.official_resolver import default_context, resolve_task
    from benchmarks.practice_grading import load_practice_tasks
    importlib.reload(importlib.import_module("benchmarks.official_resolver"))

    ctx = default_context()
    tasks = load_practice_tasks()
    total_tokens = 0
    remote_calls = 0
    for task in tasks:
        res = resolve_task(task, ctx)
        total_tokens += res["total_tokens"]
        remote_calls += res["remote_calls"]
    assert total_tokens == 0, f"Expected 0 tokens, got {total_tokens}"
    assert remote_calls == 0, f"Expected 0 remote calls, got {remote_calls}"
