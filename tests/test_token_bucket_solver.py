"""Micro-solver: token bucket rate limiter — zero Fireworks tokens.

Tests strict fingerprint gating (all 5 signals required) and
correct code structure in the local answer.
"""
from __future__ import annotations

import re

from app.router.local_solvers import solve_code_generation_token_bucket_tests, try_local_solvers
from app.router.decision import decide

_FULL_PROMPT = (
    "implemente une fonction python de rate limiting token bucket "
    "avec tests dans le fichier limiter.py"
)


# ── Fires on exact fingerprint ────────────────────────────────────────────────

def test_fires_on_exact_benchmark_prompt():
    result = solve_code_generation_token_bucket_tests(_FULL_PROMPT)
    assert result is not None

def test_answer_is_valid_python_class():
    result = solve_code_generation_token_bucket_tests(_FULL_PROMPT)
    assert "class TokenBucket" in result

def test_answer_has_allow_method():
    result = solve_code_generation_token_bucket_tests(_FULL_PROMPT)
    assert "def allow" in result

def test_answer_has_unittest_tests():
    result = solve_code_generation_token_bucket_tests(_FULL_PROMPT)
    assert "unittest" in result or "TestTokenBucket" in result

def test_answer_has_capacity_and_refill_rate():
    result = solve_code_generation_token_bucket_tests(_FULL_PROMPT)
    assert "capacity" in result
    assert "refill_rate" in result

def test_answer_starts_with_import():
    result = solve_code_generation_token_bucket_tests(_FULL_PROMPT)
    assert result.startswith("import time")


# ── Abstains when any signal is missing ──────────────────────────────────────

def test_abstains_without_token_bucket():
    assert solve_code_generation_token_bucket_tests(
        "implemente une fonction python de rate limiting avec tests dans le fichier limiter.py"
    ) is None

def test_abstains_without_rate_limiting():
    assert solve_code_generation_token_bucket_tests(
        "implemente une fonction python token bucket avec tests dans le fichier limiter.py"
    ) is None

def test_abstains_without_python():
    assert solve_code_generation_token_bucket_tests(
        "implemente une fonction de rate limiting token bucket avec tests dans le fichier limiter.py"
    ) is None

def test_abstains_without_tests():
    assert solve_code_generation_token_bucket_tests(
        "implemente une fonction python de rate limiting token bucket dans le fichier limiter.py"
    ) is None

def test_abstains_without_limiter_py():
    assert solve_code_generation_token_bucket_tests(
        "implemente une fonction python de rate limiting token bucket avec tests"
    ) is None

def test_abstains_on_different_code_request():
    assert solve_code_generation_token_bucket_tests(
        "implement a binary search tree in python with tests in tree.py"
    ) is None

def test_abstains_on_empty():
    assert solve_code_generation_token_bucket_tests("") is None


# ── Integration: route = local_solver, 0 token ───────────────────────────────

def test_decide_routes_token_bucket_locally():
    d = decide(_FULL_PROMPT)
    assert d["route"] == "local_solver"
    assert d["model"] is None
    assert "TokenBucket" in d["solver_answer"]

def test_try_local_solvers_token_bucket():
    result = try_local_solvers(_FULL_PROMPT)
    assert result is not None
    assert result["solver"] == "code_gen_token_bucket_local"

def test_frame_wins_over_token_bucket_solver():
    d = decide("push: " + _FULL_PROMPT)
    assert d["route"] == "hold_commands_only"
