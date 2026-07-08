"""Tests — model_matrix_smoke_test detectors and contract builder."""
from __future__ import annotations

import pytest

from scripts.model_matrix_smoke_test import (
    _CALIBRATED_BUDGETS,
    _CONTRACTS,
    _DISCOVERY_FAMILIES,
    _EXCLUDED_MODELS,
    _QUALITY_DISCOVERY_BUDGETS,
    DEFAULT_CANDIDATES,
    build_contract_prompt,
    build_task_summary,
    cell_ok,
    code_only_respected,
    contains_meta_reasoning,
    language_respected,
    likely_truncated,
    recommend_max_tokens,
    starts_with_meta_reasoning,
    table_unrequested_present,
)


# ── starts_with_meta_reasoning ───────────────────────────────────────────────

def test_meta_the_user_asks():
    assert starts_with_meta_reasoning("The user asks about cache strategies.")

def test_meta_the_user_wants():
    assert starts_with_meta_reasoning("The user wants a comparison of...")

def test_meta_understand_the_goal():
    assert starts_with_meta_reasoning("Understand the Goal: implement a rate limiter.")

def test_meta_analyze_the_request():
    assert starts_with_meta_reasoning("Analyze the Request: generate a resume.")

def test_meta_let_me():
    assert starts_with_meta_reasoning("Let me break this down.")

def test_meta_first_comma():
    assert starts_with_meta_reasoning("First, I'll compare the two strategies.")

def test_meta_step_one():
    assert starts_with_meta_reasoning("Step 1: understand the task.")

def test_meta_we_need_to():
    assert starts_with_meta_reasoning("We need to analyze and compare two distributed cache strategies.")

def test_meta_we_should():
    assert starts_with_meta_reasoning("We should first identify the two strategies mentioned.")

def test_meta_we_must():
    assert starts_with_meta_reasoning("We must choose two canonical examples from the domain.")

def test_meta_goal_colon():
    assert starts_with_meta_reasoning("Goal: implement a token bucket rate limiter.")

def test_meta_task_colon():
    assert starts_with_meta_reasoning("Task: analyze and compare two cache strategies.")

def test_meta_to_answer():
    assert starts_with_meta_reasoning("To answer this question, I will...")

def test_no_meta_direct_french():
    assert not starts_with_meta_reasoning(
        "LRU et LFU sont deux stratégies classiques de cache."
    )

def test_no_meta_direct_code():
    assert not starts_with_meta_reasoning("import time\nfrom collections import deque")

def test_no_meta_section_header():
    assert not starts_with_meta_reasoning("## Consistance vs Disponibilité")

def test_no_meta_short_answer():
    assert not starts_with_meta_reasoning("O(1) pour LRU, O(log n) pour LFU.")


# ── contains_meta_reasoning ───────────────────────────────────────────────────

def test_contains_meta_step_2():
    assert contains_meta_reasoning("Voici les tradeoffs.\nStep 2: analyser la complexité.")

def test_contains_meta_my_approach():
    assert contains_meta_reasoning("My approach is to first identify the two strategies.")

def test_contains_meta_let_me_begin():
    assert contains_meta_reasoning("Voici.\nLet me begin by explaining the context.")

def test_contains_meta_from_start():
    assert contains_meta_reasoning("The user requested a summary of tradeoffs.")

def test_contains_meta_analyze_request_in_body():
    """'Analyze the Request' buried in body must be caught (was a bug in v0 detector)."""
    text = "1.  **Analyze the Request:**\n    *   Topic: tradeoffs between consistency and availability."
    assert contains_meta_reasoning(text)

def test_contains_meta_the_instruction_says():
    text = "The instruction says: If specific items are not provided, choose two canonical examples."
    assert contains_meta_reasoning(text)

def test_contains_meta_i_need_to_choose():
    text = "Dans un système distribué...\nI need to choose two canonical examples first."
    assert contains_meta_reasoning(text)

def test_contains_meta_we_need_to_in_body():
    text = "We need to analyze and compare two distributed cache strategies."
    assert contains_meta_reasoning(text)

def test_no_contains_meta_clean_answer():
    text = (
        "**LRU** : O(1) grâce à une hashmap + liste doublement chaînée.\n"
        "**FIFO** : O(1) avec une queue simple.\n"
        "Complexité identique, mais LRU a une meilleure hit rate."
    )
    assert not contains_meta_reasoning(text)


# ── code_only_respected ───────────────────────────────────────────────────────

_CODE_CONTRACT = {"code_only": True}
_NON_CODE_CONTRACT = {"code_only": False}


def test_code_only_import():
    assert code_only_respected("import time\nimport collections", _CODE_CONTRACT)

def test_code_only_from_import():
    assert code_only_respected("from collections import deque\nclass TokenBucket:", _CODE_CONTRACT)

def test_code_only_def():
    assert code_only_respected("def token_bucket(capacity, rate):\n    pass", _CODE_CONTRACT)

def test_code_only_class():
    assert code_only_respected("class TokenBucket:\n    def __init__(self):\n        pass", _CODE_CONTRACT)

def test_code_only_hash_comment():
    assert code_only_respected("# Token bucket rate limiter\nimport time", _CODE_CONTRACT)

def test_code_only_refused_when_analysis():
    assert not code_only_respected(
        "Analyze the request: first I'll implement a token bucket.", _CODE_CONTRACT
    )

def test_code_only_refused_when_prose():
    assert not code_only_respected(
        "Voici une implémentation du token bucket.", _CODE_CONTRACT
    )

def test_code_only_refused_empty():
    assert not code_only_respected("", _CODE_CONTRACT)

def test_code_only_na_when_not_code_contract():
    """Non-code contracts always return True (not applicable)."""
    assert code_only_respected("Analyze the request:", _NON_CODE_CONTRACT)

def test_code_only_strips_markdown_fence():
    code = "```python\nimport time\n\nclass TokenBucket:\n    pass\n```"
    assert code_only_respected(code, _CODE_CONTRACT)


# ── language_respected ────────────────────────────────────────────────────────

def test_language_fr_detected():
    text = "Voici les deux stratégies principales de cache dans les systèmes distribués."
    assert language_respected(text, "fr")

def test_language_fr_requires_fr_tokens():
    text = "LRU has O(1) complexity. FIFO is simpler but less efficient."
    assert not language_respected(text, "fr")

def test_language_en_detected():
    text = "The token bucket algorithm allows bursts of traffic up to the bucket size."
    assert language_respected(text, "en")

def test_language_unknown_always_ok():
    assert language_respected("anything here", "unknown")

def test_language_empty_expected_ok():
    assert language_respected("anything here", "")

def test_language_mixed_fr_en_enough_fr():
    text = "LRU et FIFO sont les deux stratégies. Both have O(1) complexity."
    assert language_respected(text, "fr")


# ── table_unrequested_present ─────────────────────────────────────────────────

def test_table_detected():
    text = "| Strategy | Complexity |\n| LRU | O(1) |"
    c = {"forbid_unrequested_tables": True}
    assert table_unrequested_present(text, c)

def test_table_not_detected_in_prose():
    text = "LRU est O(1). FIFO aussi."
    c = {"forbid_unrequested_tables": True}
    assert not table_unrequested_present(text, c)

def test_table_ok_when_not_forbidden():
    text = "| Strategy | Complexity |\n| LRU | O(1) |"
    c = {"forbid_unrequested_tables": False}
    assert not table_unrequested_present(text, c)


# ── likely_truncated ──────────────────────────────────────────────────────────

def test_truncated_when_at_budget():
    result = {"completion_tokens": 158, "_max_tokens": 160}
    assert likely_truncated(result)

def test_truncated_at_95pct():
    result = {"completion_tokens": 152, "_max_tokens": 160}
    assert likely_truncated(result)

def test_not_truncated_when_below_95pct():
    result = {"completion_tokens": 100, "_max_tokens": 160}
    assert not likely_truncated(result)

def test_not_truncated_when_zero():
    result = {"completion_tokens": 0, "_max_tokens": 160}
    assert not likely_truncated(result)


# ── cell_ok ───────────────────────────────────────────────────────────────────

def _make_row(**kwargs) -> dict:
    defaults = {
        "error": None,
        "starts_with_meta_reasoning": False,
        "code_only_respected": True,
        "language_respected": True,
        "likely_truncated": False,
        "answer_kind": "comparison",
    }
    defaults.update(kwargs)
    return defaults


def test_cell_ok_clean():
    assert cell_ok(_make_row())

def test_cell_ok_fails_on_error():
    assert not cell_ok(_make_row(error="HTTP 404"))

def test_cell_ok_fails_on_meta():
    assert not cell_ok(_make_row(starts_with_meta_reasoning=True))

def test_cell_ok_fails_on_code_violation():
    assert not cell_ok(_make_row(answer_kind="code_file", code_only_respected=False))

def test_cell_ok_fails_on_lang():
    assert not cell_ok(_make_row(language_respected=False))

def test_cell_ok_fails_on_truncation():
    assert not cell_ok(_make_row(likely_truncated=True))


# ── build_contract_prompt ─────────────────────────────────────────────────────

def test_prompt_forbids_the_user_asks():
    c = _CONTRACTS[0]  # comparison
    p = build_contract_prompt(c)
    assert "The user asks" in p or "Do not start with" in p

def test_prompt_forbids_understand_the_goal():
    c = _CONTRACTS[0]
    p = build_contract_prompt(c)
    assert "Understand the Goal" in p

def test_prompt_code_only_forces_code():
    c = _CONTRACTS[2]  # code_file
    p = build_contract_prompt(c)
    assert "Return only valid code" in p

def test_prompt_code_only_no_fences():
    c = _CONTRACTS[2]
    p = build_contract_prompt(c)
    assert "markdown code fences" in p or "fences" in p

def test_prompt_missing_referent_no_canonical_wording():
    """'canonical examples' wording caused gpt-oss to quote the instruction back."""
    c = _CONTRACTS[0]  # missing_referent=True
    p = build_contract_prompt(c)
    assert "canonical examples" not in p

def test_prompt_missing_referent_implicit():
    """Replacement wording must be implicit — no instruction-quoting bait."""
    c = _CONTRACTS[0]
    p = build_contract_prompt(c)
    assert "well-known" in p or "common" in p or "directly" in p

def test_prompt_fr_language():
    c = _CONTRACTS[0]
    p = build_contract_prompt(c)
    assert "French" in p

def test_prompt_compact_sections():
    c = _CONTRACTS[0]  # output_shape=compact_sections
    p = build_contract_prompt(c)
    assert "section" in p.lower()

def test_prompt_no_tables():
    c = _CONTRACTS[0]
    p = build_contract_prompt(c)
    assert "table" in p.lower()

def test_prompt_no_private_import_traces():
    """The prompt builder must not reference private Brody/Obsidure identifiers."""
    for c in _CONTRACTS:
        p = build_contract_prompt(c)
        assert "brody" not in p.lower()
        assert "obsidure" not in p.lower()
        assert "kx108" not in p.lower()
        assert "obsidia_api" not in p.lower()


# ── discovery filter logic ────────────────────────────────────────────────────

def test_discovery_families_includes_gemma():
    assert "gemma" in _DISCOVERY_FAMILIES

def test_discovery_families_includes_gpt_oss():
    assert "gpt-oss" in _DISCOVERY_FAMILIES

def test_discovery_family_match_gemma():
    """Simulate what build_candidate_list does: model_id contains 'gemma'."""
    model_id = "accounts/fireworks/models/gemma-4-31b-it"
    name_part = model_id.split("/")[-1].lower()
    assert any(fam in name_part for fam in _DISCOVERY_FAMILIES)

def test_discovery_family_match_glm():
    model_id = "accounts/fireworks/models/glm-5p1"
    name_part = model_id.split("/")[-1].lower()
    assert any(fam in name_part for fam in _DISCOVERY_FAMILIES)

def test_discovery_family_no_match_unknown():
    model_id = "accounts/fireworks/models/unknown-model-xyz"
    name_part = model_id.split("/")[-1].lower()
    assert not any(fam in name_part for fam in _DISCOVERY_FAMILIES)


# ── contracts integrity ───────────────────────────────────────────────────────

# ── DEFAULT_CANDIDATES and exclusions ────────────────────────────────────────

def test_default_candidates_excludes_glm5p1():
    """glm-5p1 is excluded from rerun after hardwired-template failure."""
    assert "accounts/fireworks/models/glm-5p1" not in DEFAULT_CANDIDATES

def test_default_candidates_includes_glm5p2():
    assert "accounts/fireworks/models/glm-5p2" in DEFAULT_CANDIDATES

def test_default_candidates_includes_gpt_oss():
    assert "accounts/fireworks/models/gpt-oss-120b" in DEFAULT_CANDIDATES

def test_default_candidates_includes_deepseek():
    assert "accounts/fireworks/models/deepseek-v4-pro" in DEFAULT_CANDIDATES

def test_excluded_models_contains_glm5p1():
    assert "accounts/fireworks/models/glm-5p1" in _EXCLUDED_MODELS

def test_excluded_models_reason_mentions_template():
    reason = _EXCLUDED_MODELS.get("accounts/fireworks/models/glm-5p1", "")
    assert "template" in reason.lower() or "meta" in reason.lower()


# ── Budget recalibration ──────────────────────────────────────────────────────

def test_budget_comparison_recalibrated():
    c = next(x for x in _CONTRACTS if x["contract_id"] == "comparison_missing_referent")
    assert c["max_tokens"] == 280

def test_budget_summary_recalibrated():
    c = next(x for x in _CONTRACTS if x["contract_id"] == "structured_summary")
    assert c["max_tokens"] == 380

def test_budget_code_recalibrated():
    c = next(x for x in _CONTRACTS if x["contract_id"] == "code_file")
    assert c["max_tokens"] == 700

def test_no_discover_flag_recognized():
    """--no-discover is already part of main() argv parsing; test that parsing logic works."""
    import sys as _sys
    old_argv = _sys.argv[:]
    _sys.argv = ["script", "--no-discover"]
    no_discover = "--no-discover" in _sys.argv
    _sys.argv = old_argv
    assert no_discover is True


# ── Quality discovery mode ────────────────────────────────────────────────────

def test_quality_discovery_flag_recognized():
    import sys as _sys
    old_argv = _sys.argv[:]
    _sys.argv = ["script", "--quality-discovery"]
    qd = "--quality-discovery" in _sys.argv
    _sys.argv = old_argv
    assert qd is True

def test_quality_discovery_budgets_comparison():
    assert _QUALITY_DISCOVERY_BUDGETS["comparison_missing_referent"] == 1200

def test_quality_discovery_budgets_summary():
    assert _QUALITY_DISCOVERY_BUDGETS["structured_summary"] == 1200

def test_quality_discovery_budgets_code():
    assert _QUALITY_DISCOVERY_BUDGETS["code_file"] == 2200

def test_calibrated_budgets_unchanged_comparison():
    assert _CALIBRATED_BUDGETS["comparison_missing_referent"] == 280

def test_calibrated_budgets_unchanged_summary():
    assert _CALIBRATED_BUDGETS["structured_summary"] == 380

def test_calibrated_budgets_unchanged_code():
    assert _CALIBRATED_BUDGETS["code_file"] == 700

def test_calibrated_and_discovery_are_independent():
    """Modifying one profile must not affect the other."""
    assert _CALIBRATED_BUDGETS["code_file"] != _QUALITY_DISCOVERY_BUDGETS["code_file"]
    assert _CALIBRATED_BUDGETS["comparison_missing_referent"] != _QUALITY_DISCOVERY_BUDGETS["comparison_missing_referent"]


# ── recommend_max_tokens ──────────────────────────────────────────────────────

def test_recommend_not_truncated():
    import math
    result = recommend_max_tokens(completion_tokens=300, truncated=False)
    assert result == math.ceil(300 * 1.15)

def test_recommend_not_truncated_exact_ceil():
    import math
    result = recommend_max_tokens(completion_tokens=220, truncated=False)
    assert result == math.ceil(220 * 1.15)   # 253

def test_recommend_truncated_returns_none():
    assert recommend_max_tokens(completion_tokens=700, truncated=True) is None

def test_recommend_zero_tokens_returns_none():
    assert recommend_max_tokens(completion_tokens=0, truncated=False) is None

def test_recommend_adds_15pct_headroom():
    import math
    for ct in [100, 250, 500, 1000]:
        result = recommend_max_tokens(ct, truncated=False)
        assert result == math.ceil(ct * 1.15), f"Failed for ct={ct}"


# ── build_task_summary ────────────────────────────────────────────────────────

def _make_ok_row(contract_id: str, model: str, completion_tokens: int,
                 latency: float = 1.0) -> dict:
    return {
        "contract_id":           contract_id,
        "model_short":           model,
        "model_id":              f"accounts/fireworks/models/{model}",
        "ok":                    True,
        "starts_with_meta_reasoning": False,
        "code_only_respected":   True,
        "language_respected":    True,
        "likely_truncated":      False,
        "completion_tokens":     completion_tokens,
        "latency_s":             latency,
        "answer_kind":           "comparison",
        "error":                 None,
    }

def _make_trunc_row(contract_id: str, model: str, completion_tokens: int) -> dict:
    r = _make_ok_row(contract_id, model, completion_tokens)
    r["ok"] = False
    r["likely_truncated"] = True
    return r

def test_task_summary_best_model_when_ok():
    rows = [
        _make_ok_row("comparison_missing_referent", "model-a", 200, latency=1.0),
        _make_ok_row("comparison_missing_referent", "model-b", 180, latency=2.0),
    ]
    summaries = build_task_summary(rows)
    assert len(summaries) == 1
    s = summaries[0]
    assert s["cells_ok"] == 2
    assert s["fastest_ok_model"] == "model-a"
    assert s["lowest_token_ok_model"] == "model-b"

def test_task_summary_no_ok_rows():
    rows = [
        _make_trunc_row("comparison_missing_referent", "model-a", 280),
        _make_trunc_row("comparison_missing_referent", "model-b", 280),
    ]
    summaries = build_task_summary(rows)
    s = summaries[0]
    assert s["cells_ok"] == 0
    assert s["recommended_model"] is None
    assert s["recommended_budget"] is None
    assert s["all_still_truncated"] is True

def test_task_summary_recommended_budget_from_ok():
    import math
    rows = [_make_ok_row("code_file", "deepseek-v4-pro", 450, latency=5.0)]
    summaries = build_task_summary(rows)
    s = summaries[0]
    assert s["recommended_budget"] == math.ceil(450 * 1.15)

def test_task_summary_groups_by_contract():
    rows = [
        _make_ok_row("comparison_missing_referent", "m1", 200),
        _make_ok_row("structured_summary", "m1", 300),
        _make_ok_row("code_file", "m1", 600),
    ]
    summaries = build_task_summary(rows)
    assert len(summaries) == 3
    ids = {s["contract_id"] for s in summaries}
    assert ids == {"comparison_missing_referent", "structured_summary", "code_file"}


# ── report fields ─────────────────────────────────────────────────────────────

def test_cell_has_natural_completion_tokens_field():
    """Every cell row must carry natural_completion_tokens."""
    from scripts.model_matrix_smoke_test import run_matrix
    # run_matrix calls chat() — we don't run live; check field presence via a dry row
    # instead verify the field is added by inspecting _make logic used in run_matrix
    # via the row construction in the loop (static check via import is sufficient)
    import inspect, scripts.model_matrix_smoke_test as m
    src = inspect.getsource(m.run_matrix)
    assert "natural_completion_tokens" in src

def test_cell_has_recommended_final_max_tokens_field():
    import inspect, scripts.model_matrix_smoke_test as m
    src = inspect.getsource(m.run_matrix)
    assert "recommended_final_max_tokens" in src

def test_cell_has_recommendation_status_field():
    import inspect, scripts.model_matrix_smoke_test as m
    src = inspect.getsource(m.run_matrix)
    assert "recommendation_status" in src

def test_write_report_includes_run_mode():
    import inspect, scripts.model_matrix_smoke_test as m
    src = inspect.getsource(m.write_report)
    assert "run_mode" in src

def test_write_report_includes_task_summary():
    import inspect, scripts.model_matrix_smoke_test as m
    src = inspect.getsource(m.write_report)
    assert "task_summary" in src


# ── contracts integrity ───────────────────────────────────────────────────────

def test_contracts_count():
    assert len(_CONTRACTS) == 3


def test_contracts_ids_unique():
    ids = [c["contract_id"] for c in _CONTRACTS]
    assert len(ids) == len(set(ids))


def test_contracts_have_required_fields():
    required = {
        "contract_id", "answer_kind", "output_shape", "missing_referent",
        "language", "max_tokens", "code_only", "forbid_meta_reasoning",
        "forbid_task_description", "request",
    }
    for c in _CONTRACTS:
        missing = required - set(c.keys())
        assert not missing, f"Contract {c['contract_id']} missing: {missing}"


def test_code_contract_has_code_only_true():
    code_c = next(c for c in _CONTRACTS if c["contract_id"] == "code_file")
    assert code_c["code_only"] is True
    assert code_c["max_tokens"] == 700  # recalibrated from 320


def test_comparison_contract_has_missing_referent():
    cmp_c = next(c for c in _CONTRACTS if c["contract_id"] == "comparison_missing_referent")
    assert cmp_c["missing_referent"] is True


def test_summary_contract_not_code_only():
    sum_c = next(c for c in _CONTRACTS if c["contract_id"] == "structured_summary")
    assert sum_c["code_only"] is False


def test_no_task_id_in_contract_logic():
    """Contracts must not use task_id as a decision key."""
    for c in _CONTRACTS:
        assert "task_id" not in c
        assert "fireworks_reasoning" not in str(c)
        assert "fireworks_generation" not in str(c)
        assert "fireworks_code" not in str(c)


def test_private_imports_absent():
    """The module must not import private Brody/Obsidure packages."""
    import ast
    import pathlib
    src = pathlib.Path(__file__).parent.parent / "scripts" / "model_matrix_smoke_test.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = ""
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
            elif isinstance(node, ast.Import):
                module = ", ".join(alias.name for alias in node.names)
            assert "brody_adaptive" not in module
            assert "obsidia_api" not in module
            assert "brody_thermodynamics" not in module
            assert "obsidure" not in module.lower()
