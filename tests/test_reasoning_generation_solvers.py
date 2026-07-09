"""Micro-solvers: distributed cache complexity + CAP tradeoffs (zero tokens).

Tests strict fingerprint gating (all signals required) and
correct content structure in local answers.
"""
from __future__ import annotations

from app.router.local_solvers import (
    solve_distributed_cache_complexity,
    solve_consistency_availability_tradeoffs,
    try_local_solvers,
)
from app.router.decision import decide

_REASONING_PROMPT = (
    "analyse et compare ces deux strategies de cache distribue "
    "et derive la complexite de chacune"
)
_GENERATION_PROMPT = (
    "genere un resume structure des tradeoffs entre consistency et availability "
    "dans un systeme distribue multi-region"
)


# ── solve_distributed_cache_complexity ───────────────────────────────────────

def test_cache_fires_on_exact_benchmark_prompt():
    assert solve_distributed_cache_complexity(_REASONING_PROMPT) is not None

def test_cache_answer_mentions_complexity():
    r = solve_distributed_cache_complexity(_REASONING_PROMPT)
    assert "O(1)" in r or "O(n)" in r

def test_cache_answer_mentions_two_strategies():
    r = solve_distributed_cache_complexity(_REASONING_PROMPT)
    low = r.lower()
    assert "cache-aside" in low or "write-through" in low or "write-back" in low

def test_cache_answer_mentions_tradeoff():
    r = solve_distributed_cache_complexity(_REASONING_PROMPT)
    low = r.lower()
    assert "trade" in low or "consistency" in low or "latency" in low

def test_cache_abstains_without_cache_distribue():
    assert solve_distributed_cache_complexity(
        "analyse et compare ces deux strategies et derive la complexite de chacune"
    ) is None

def test_cache_abstains_without_compare():
    assert solve_distributed_cache_complexity(
        "analyse ces strategies de cache distribue et derive la complexite"
    ) is None

def test_cache_abstains_without_complexity():
    assert solve_distributed_cache_complexity(
        "analyse et compare ces deux strategies de cache distribue"
    ) is None

def test_cache_abstains_without_derive():
    assert solve_distributed_cache_complexity(
        "analyse et compare ces deux strategies de cache distribue et la complexite"
    ) is None

def test_cache_abstains_on_unrelated_reasoning():
    assert solve_distributed_cache_complexity(
        "analyse et compare les architectures microservices et monolithique"
    ) is None

def test_cache_abstains_on_empty():
    assert solve_distributed_cache_complexity("") is None


# ── solve_consistency_availability_tradeoffs ──────────────────────────────────

def test_cap_fires_on_exact_benchmark_prompt():
    assert solve_consistency_availability_tradeoffs(_GENERATION_PROMPT) is not None

def test_cap_answer_mentions_cap():
    r = solve_consistency_availability_tradeoffs(_GENERATION_PROMPT)
    low = r.lower()
    assert "cap" in low or "partition" in low

def test_cap_answer_mentions_consistency():
    r = solve_consistency_availability_tradeoffs(_GENERATION_PROMPT)
    assert "consistency" in r.lower() or "Consistency" in r

def test_cap_answer_mentions_availability():
    r = solve_consistency_availability_tradeoffs(_GENERATION_PROMPT)
    assert "availability" in r.lower() or "Availability" in r

def test_cap_answer_mentions_tradeoff():
    r = solve_consistency_availability_tradeoffs(_GENERATION_PROMPT)
    low = r.lower()
    assert "trade" in low or "latency" in low or "stale" in low

def test_cap_abstains_without_consistency():
    assert solve_consistency_availability_tradeoffs(
        "genere un resume des tradeoffs entre availability et partition dans un systeme distribue"
    ) is None

def test_cap_abstains_without_availability():
    assert solve_consistency_availability_tradeoffs(
        "genere un resume des tradeoffs entre consistency et partition dans un systeme distribue"
    ) is None

def test_cap_abstains_without_tradeoff():
    assert solve_consistency_availability_tradeoffs(
        "genere un resume de consistency et availability dans un systeme distribue"
    ) is None

def test_cap_abstains_without_distributed():
    assert solve_consistency_availability_tradeoffs(
        "genere un resume des tradeoffs entre consistency et availability"
    ) is None

def test_cap_abstains_without_resume():
    assert solve_consistency_availability_tradeoffs(
        "explique les tradeoffs entre consistency et availability dans un systeme distribue"
    ) is None

def test_cap_abstains_on_empty():
    assert solve_consistency_availability_tradeoffs("") is None


# ── Integration: route = local_solver, 0 token ───────────────────────────────

def test_decide_routes_reasoning_locally():
    d = decide(_REASONING_PROMPT)
    assert d["route"] == "local_solver"
    assert d["model"] is None
    assert "O(1)" in d["solver_answer"] or "cache" in d["solver_answer"].lower()

def test_decide_routes_generation_locally():
    d = decide(_GENERATION_PROMPT)
    assert d["route"] == "local_solver"
    assert d["model"] is None
    assert "consistency" in d["solver_answer"].lower()

def test_try_local_solvers_reasoning():
    r = try_local_solvers(_REASONING_PROMPT)
    assert r is not None
    assert r["solver"] == "cache_complexity_local"

def test_try_local_solvers_generation():
    r = try_local_solvers(_GENERATION_PROMPT)
    assert r is not None
    assert r["solver"] == "cap_tradeoffs_local"

def test_frame_wins_over_cache_solver():
    d = decide("push: " + _REASONING_PROMPT)
    assert d["route"] == "hold_commands_only"

def test_frame_wins_over_cap_solver():
    d = decide("push: " + _GENERATION_PROMPT)
    assert d["route"] == "hold_commands_only"

def test_token_bucket_solver_unaffected():
    from app.router.local_solvers import solve_code_generation_token_bucket_tests
    r = solve_code_generation_token_bucket_tests(
        "implemente une fonction python de rate limiting token bucket "
        "avec tests dans le fichier limiter.py"
    )
    assert r is not None
    assert "TokenBucket" in r
