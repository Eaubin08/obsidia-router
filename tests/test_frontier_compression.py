"""Tests pour la couche de compression frontier (build_compact_override).

Doctrine:
- build_compact_override() ne change jamais les routes
- completion_budget est toujours dans [64, profile_cap]
- les system prompts compacts sont non-vides pour chaque kind
- les 8 practice tasks restent 8/8 local, 0 token après intégration
- false_local_closures = 0 inchangé
- le champ compression_applied=True est tracé dans les metrics Fireworks
"""
from __future__ import annotations

import importlib
import pytest

from benchmarks.track1_remote_answer_contract import (
    _COMPACT_CAP,
    _COMPACT_SYSTEM,
    _COMPACT_TARGET,
    build_compact_override,
    classify_answer_kind,
)


# ── 1. Formule du budget ──────────────────────────────────────────────────────

@pytest.mark.parametrize("kind,prompt,expected_cap", [
    ("direct_answer",      "What is the capital of Zylophoria?", 200),
    ("comparison",         "Compare microservices and monolithic architectures.", 220),
    ("structured_summary", "resume en une phrase", 180),
    ("code_file",          "implement a binary search tree in Python", 340),
    ("clarification",      "ok", 60),
])
def test_completion_budget_never_exceeds_profile_cap(kind, prompt, expected_cap):
    result = build_compact_override(prompt, kind)
    assert result["completion_budget"] <= expected_cap


def test_completion_budget_never_below_64():
    # Très long prompt : le budget ne doit pas tomber sous 64
    long_prompt = "x" * 2000
    result = build_compact_override(long_prompt, "direct_answer")
    assert result["completion_budget"] >= 64


def test_completion_budget_formula_direct_short():
    # Prompt court ~35 chars → estimated_tokens ≈ 8
    request = "What is the capital of Zylophoria?"
    result = build_compact_override(request, "direct_answer")
    est = len(request) // 4
    target = _COMPACT_TARGET["direct_answer"]
    cap = _COMPACT_CAP["direct_answer"]
    expected = min(cap, max(64, target - est))
    assert result["completion_budget"] == expected


def test_completion_budget_formula_code():
    request = "implement a binary search tree in Python with insert and search methods"
    result = build_compact_override(request, "code_file")
    est = len(request) // 4
    target = _COMPACT_TARGET["code_file"]
    cap = _COMPACT_CAP["code_file"]
    expected = min(cap, max(64, target - est))
    assert result["completion_budget"] == expected


def test_estimated_prompt_tokens_equals_len_div4():
    request = "Compare these two strategies."
    result = build_compact_override(request, "comparison")
    assert result["estimated_prompt_tokens"] == len(request) // 4


def test_compact_applied_always_true():
    for kind in ("direct_answer", "comparison", "code_file",
                 "structured_summary", "clarification"):
        assert build_compact_override("test prompt", kind)["compact_applied"] is True


# ── 2. System prompts compacts ────────────────────────────────────────────────

@pytest.mark.parametrize("kind", [
    "direct_answer", "comparison", "structured_summary", "code_file", "clarification",
])
def test_compact_system_not_empty(kind):
    result = build_compact_override("any request", kind)
    assert result["compact_system"].strip()


def test_compact_system_code_starts_with_def_or_class():
    result = build_compact_override("implement a BST", "code_file")
    assert "def" in result["compact_system"] or "class" in result["compact_system"]


def test_compact_system_comparison_has_bullets():
    result = build_compact_override("compare A and B", "comparison")
    assert "A:" in result["compact_system"] or "bullet" in result["compact_system"].lower()


def test_compact_system_direct_no_chain_of_thought():
    result = build_compact_override("what is X?", "direct_answer")
    assert "chain-of-thought" in result["compact_system"].lower()


def test_compact_system_unknown_kind_uses_direct_fallback():
    result = build_compact_override("anything", "unknown_kind")
    assert result["compact_system"] == _COMPACT_SYSTEM["direct_answer"]
    assert result["completion_budget"] >= 64


# ── 3. Routes inchangées — aucune fermeture locale non voulue ─────────────────

def test_compact_override_does_not_affect_local_routes(monkeypatch):
    """build_compact_override() ne change pas la décision de routage."""
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    from app.router.decision import decide
    prompt = "What is the capital of Australia?"
    decision = decide(prompt)
    # la route est determinée AVANT compact_override — elle doit être locale
    assert decision["route"] == "local_solver"
    # le compact override est calculé mais ne change pas la route
    compact = build_compact_override(prompt, "direct_answer")
    assert compact["compact_applied"] is True
    # route inchangée
    assert decide(prompt)["route"] == "local_solver"


def test_compact_override_does_not_close_near_boundary(monkeypatch):
    """Un cas near_boundary doit rester Fireworks — compact ne ferme pas localement."""
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    from app.router.local_solvers import try_local_solvers
    prompt = "implemente une fonction python de rate limiting token bucket avec tests"
    local = try_local_solvers(prompt)
    # Ce cas doit abstraire (None) — compact ne change pas ça
    assert local is None


# ── 4. Official practice 8/8 local, 0 token ──────────────────────────────────

def test_official_practice_still_zero_tokens_after_compact(monkeypatch):
    """Les 8 tasks practice restent 8/8 local, 0 token avec la couche compact."""
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    from app.adapters import fireworks as fw
    importlib.reload(fw)

    from benchmarks.official_resolver import RuntimeContext, resolve_task
    from benchmarks.practice_grading import load_practice_tasks

    ctx = RuntimeContext(allowed_models=["accounts/fireworks/models/gpt-oss-120b"])
    tasks = load_practice_tasks()
    total_tokens = 0
    remote_calls = 0
    for task in tasks:
        r = resolve_task({"task_id": task["task_id"], "prompt": task["prompt"]}, ctx)
        total_tokens += r.get("total_tokens", 0)
        remote_calls += r.get("remote_calls", 0)

    assert total_tokens == 0, f"Expected 0 tokens, got {total_tokens}"
    assert remote_calls == 0, f"Expected 0 remote calls, got {remote_calls}"


# ── 5. false_local_closures = 0 ──────────────────────────────────────────────

def test_false_local_closures_zero_on_fireworks_frontier():
    """Les cas near_boundary qui doivent aller en Fireworks ne ferment pas localement."""
    from app.router.local_solvers import try_local_solvers

    fireworks_prompts = [
        "implemente une fonction python de rate limiting token bucket avec tests",
        "explique les tradeoffs entre consistency et availability dans un systeme distribue",
        "analyse et compare ces deux strategies de cache distribue",
        "Extract all named entities from: Xylophorus visited Qbrtz last Flurpday.",
        "implement a binary search tree in Python with insert and search methods and tests in bst.py",
        "What is the capital of Zylophoria?",
    ]
    for prompt in fireworks_prompts:
        result = try_local_solvers(prompt)
        assert result is None, (
            f"false_local_closure: '{prompt[:50]}' closed locally but should go to Fireworks"
        )


# ── 6. Métriques surfacées ────────────────────────────────────────────────────

def test_compact_metadata_fields_present():
    result = build_compact_override("Design a rate limiting strategy.", "direct_answer")
    assert "completion_budget" in result
    assert "compact_system" in result
    assert "estimated_prompt_tokens" in result
    assert "profile_cap" in result
    assert "target_total_tokens" in result
    assert "compact_applied" in result
    assert "compact_profile" in result


def test_compact_profile_matches_kind():
    for kind in ("direct_answer", "comparison", "code_file"):
        result = build_compact_override("any prompt", kind)
        assert result["compact_profile"] == kind


def test_target_total_tokens_matches_table():
    for kind, expected_target in _COMPACT_TARGET.items():
        result = build_compact_override("some prompt", kind)
        assert result["target_total_tokens"] == expected_target


# ── 7. Budget total estimé pour les 12 cas frontier ─────────────────────────

@pytest.mark.parametrize("task_id,prompt,kind,expected_budget_max", [
    ("nb_token_bucket_no_limiterpy",
     "implemente une fonction python de rate limiting token bucket avec tests",
     "code_file", 340),
    ("nb_cap_no_summary",
     "explique les tradeoffs entre consistency et availability dans un systeme distribue",
     "direct_answer", 200),
    ("nb_cache_no_complexity",
     "analyse et compare ces deux strategies de cache distribue",
     "comparison", 220),
    ("nb_ner_unknown_entity",
     "Extract all named entities from: Xylophorus visited Qbrtz last Flurpday.",
     "direct_answer", 200),
    ("nb_code_different_spec",
     "implement a binary search tree in Python with insert and search methods and tests in bst.py",
     "code_file", 340),
    ("nb_capital_unknown_country",
     "What is the capital of Zylophoria?",
     "direct_answer", 200),
    ("or_arch_comparison",
     "Compare microservices and monolithic architectures for a real-time payment processing system with 10k TPS.",
     "comparison", 220),
    ("or_unknown_system",
     "Design a rate limiting strategy for a multi-tenant SaaS API with tiered quotas and burst allowances.",
     "direct_answer", 200),
    ("or_new_code",
     "Implement a thread-safe LRU cache in Python with O(1) get and put operations.",
     "code_file", 340),
    ("or_tech_plan",
     "Write a technical plan for migrating a PostgreSQL database to a distributed key-value store without downtime.",
     "direct_answer", 200),
    ("nd_typo_capital",
     "whats the capitl of australa",
     "direct_answer", 200),
    ("nd_contradiction",
     "resume en une phrase mais donne moi aussi un rapport detaille complet de 10 pages",
     "structured_summary", 180),
])
def test_frontier_budget_within_target(task_id, prompt, kind, expected_budget_max):
    result = build_compact_override(prompt, kind)
    assert result["completion_budget"] <= expected_budget_max, (
        f"{task_id}: budget {result['completion_budget']} > cap {expected_budget_max}"
    )
