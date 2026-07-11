"""Tests — Track 1 remote answer contract. Zero private imports."""
from __future__ import annotations

import inspect

import pytest

from benchmarks.track1_remote_answer_contract import (
    _DEFAULT_MODEL,
    _EXCLUDED_MODELS,
    build_contract_prompt,
    build_remote_answer_contract,
    classify_ambiguity,
    classify_answer_kind,
    classify_output_shape,
    detect_language,
    detect_missing_referent,
    select_max_tokens,
    select_model_preference,
    select_target_words,
)


# ── detect_language ──────────────────────────────────────────────────────────

def test_language_fr_by_accent():
    assert detect_language("analyse et compare ces deux stratégies") == "fr"


def test_language_fr_by_keyword_resume():
    assert detect_language("resume de maniere structuree les tradeoffs") == "fr"


def test_language_fr_by_keyword_implemente():
    assert detect_language("implemente une fonction python") == "fr"


def test_language_en_default():
    assert detect_language("explain the difference between cache strategies") == "en"


def test_language_en_no_fr_chars():
    assert detect_language("write a rate limiter in python with tests") == "en"


# ── detect_missing_referent ──────────────────────────────────────────────────

@pytest.mark.parametrize("req", [
    "analyse et compare ces deux strategies",
    "compare these two approaches",
    "as mentioned ci-dessus, compare them",
    "explain the above tradeoffs",
    "summarize the following items",
    "analyse ceux-ci en detail",
])
def test_missing_referent_detected(req):
    assert detect_missing_referent(req) is True


def test_missing_referent_not_present():
    assert detect_missing_referent("compare cache-aside and write-through strategies") is False


def test_missing_referent_none_in_code_request():
    assert detect_missing_referent("implemente un rate limiter en python avec tests") is False


# ── classify_answer_kind ─────────────────────────────────────────────────────

def test_answer_kind_code_by_implemente():
    assert classify_answer_kind("implemente une fonction python de rate limiting") == "code_file"


def test_answer_kind_code_by_implement():
    assert classify_answer_kind("implement a python rate limiter with tests") == "code_file"


def test_answer_kind_code_by_dot_py():
    assert classify_answer_kind("ecris le fichier limiter.py avec tests") == "code_file"


def test_answer_kind_structured_summary():
    assert classify_answer_kind("resume de maniere structuree les tradeoffs") == "structured_summary"


def test_answer_kind_comparison():
    assert classify_answer_kind("analyse et compare ces deux strategies de cache") == "comparison"


def test_answer_kind_comparison_by_derivation():
    assert classify_answer_kind("derive la complexite de chaque algorithme") == "comparison"


def test_answer_kind_direct_answer_fallback():
    kind = classify_answer_kind("explique le theoreme CAP")
    assert kind == "direct_answer"


# ── classify_output_shape ────────────────────────────────────────────────────

def test_output_shape_code_only():
    assert classify_output_shape("implemente une classe LRU", "code_file") == "code_only"


def test_output_shape_compact_sections():
    assert classify_output_shape("resume les tradeoffs", "structured_summary") == "compact_sections"


def test_output_shape_compact_for_comparison():
    assert classify_output_shape("compare cache-aside et write-through", "comparison") == "compact_sections"


# ── select_max_tokens ────────────────────────────────────────────────────────

def test_budget_comparison():
    assert select_max_tokens("comparison") == 420


def test_budget_structured_summary():
    assert select_max_tokens("structured_summary") == 420


def test_budget_code_file():
    assert select_max_tokens("code_file") == 620


def test_budget_direct_answer():
    assert select_max_tokens("direct_answer") == 320


def test_budget_clarification():
    assert select_max_tokens("clarification") == 80


# ── select_model_preference ──────────────────────────────────────────────────

def test_model_preference_is_gpt_oss():
    assert select_model_preference() == "accounts/fireworks/models/gpt-oss-120b"


def test_excluded_models_contains_glm5p1():
    assert "accounts/fireworks/models/glm-5p1" in _EXCLUDED_MODELS


def test_excluded_models_contains_deepseek():
    assert "accounts/fireworks/models/deepseek-v4-pro" in _EXCLUDED_MODELS


def test_excluded_models_gemma():
    assert "accounts/fireworks/models/gemma" in _EXCLUDED_MODELS


# ── build_contract_prompt ────────────────────────────────────────────────────

def test_prompt_no_canonical_examples():
    prompt = build_contract_prompt("comparison", True, False, "fr", 150)
    assert "canonical examples" not in prompt.lower()


def test_prompt_no_instruction_says():
    for ak in ("comparison", "structured_summary", "code_file", "direct_answer"):
        prompt = build_contract_prompt(ak, False, ak == "code_file", "en", 150)
        assert "instruction says" not in prompt.lower(), f"Failed for {ak}"


def test_prompt_no_the_user_asks():
    # v3f: prose prompt starts with "Final only"
    prompt = build_contract_prompt("direct_answer", False, False, "en", 60)
    assert prompt.startswith("Final only")
    assert "The user asks" not in prompt


def test_prompt_no_analyze_the_request():
    # v3f: no preamble — starts with "Final only"
    prompt = build_contract_prompt("structured_summary", False, False, "fr", 75)
    assert prompt.startswith("Final only")
    assert "Analyze the Request" not in prompt


def test_prompt_code_only_no_explanation():
    prompt = build_contract_prompt("code_file", False, True, "en", 130)
    assert "No prose" in prompt or "no prose" in prompt.lower()
    assert "no docstring" in prompt.lower()


def test_prompt_code_no_planning():
    prompt = build_contract_prompt("code_file", False, True, "fr", 130)
    assert "def" in prompt
    assert "English" in prompt


def test_prompt_fr_contains_french_instruction():
    prompt = build_contract_prompt("comparison", False, False, "fr", 150)
    # Regle AMD Track 1 : anglais obligatoire meme pour une requete FR.
    assert "Answer in English" in prompt


def test_prompt_en_contains_english_instruction():
    prompt = build_contract_prompt("comparison", False, False, "en", 150)
    assert "Answer in English" in prompt


def test_prompt_missing_referent_uses_implicit_wording():
    prompt = build_contract_prompt("comparison", True, False, "fr", 150)
    assert "well-known instances" in prompt or "common" in prompt
    assert "canonical" not in prompt.lower()


# ── build_remote_answer_contract ─────────────────────────────────────────────

def test_contract_no_task_id_param():
    sig = inspect.signature(build_remote_answer_contract)
    assert "task_id" not in sig.parameters


def test_contract_private_policy_false():
    c = build_remote_answer_contract("implemente un rate limiter")
    assert c["private_policy_imported"] is False


def test_contract_model_matrix_calibrated():
    c = build_remote_answer_contract("résume les tradeoffs CAP")
    assert c["model_matrix_calibrated"] is True
    assert c["calibration_source"] == "quality_discovery_v1"


def test_contract_budget_headroom_policy():
    c = build_remote_answer_contract("compare ces deux strategies")
    assert c["budget_headroom_policy"] == "human_margin_high_v0"


def test_contract_comparison_full():
    c = build_remote_answer_contract(
        "analyse et compare ces deux strategies de cache distribue et derive la complexite"
    )
    assert c["answer_kind"] == "comparison"
    assert c["max_tokens"] == 420
    assert c["model_preference"] == _DEFAULT_MODEL
    assert c["missing_referent"] is True
    assert "missing_referent_detected" in c["source_signals"]


def test_contract_structured_summary_full():
    c = build_remote_answer_contract(
        "resume de maniere structuree les tradeoffs consistency availability"
    )
    assert c["answer_kind"] == "structured_summary"
    assert c["max_tokens"] == 420
    assert c["model_preference"] == _DEFAULT_MODEL


def test_contract_code_file_full():
    c = build_remote_answer_contract(
        "implemente en python une fonction de rate limiting token bucket avec tests"
    )
    assert c["answer_kind"] == "code_file"
    assert c["max_tokens"] == 620
    assert c["code_only"] is True
    assert c["output_shape"] == "code_only"
    assert "tests_requested" in c["source_signals"]


def test_contract_forbid_fields():
    c = build_remote_answer_contract("résume les points clés du CAP theorem")
    assert c["forbid_meta_reasoning"] is True
    assert c["forbid_task_description"] is True
    assert c["forbid_planning"] is True
    assert c["forbid_unrequested_tables"] is True


def test_contract_version():
    c = build_remote_answer_contract("explain something")
    assert c["contract_version"] == "track1_remote_answer_contract_v0"


def test_contract_language_fr():
    c = build_remote_answer_contract("implemente une classe LRU en python")
    assert c["language"] == "fr"


def test_contract_language_en():
    c = build_remote_answer_contract("implement a rate limiter in python")
    assert c["language"] == "en"


def test_contract_source_signals_present():
    c = build_remote_answer_contract("implement a python function")
    assert isinstance(c["source_signals"], list)
    assert len(c["source_signals"]) > 0


def test_contract_risk_flags_code():
    c = build_remote_answer_contract("implemente en python une classe LRU")
    assert "truncation_risk_code" in c["risk_flags"]


def test_contract_risk_flags_missing_referent():
    c = build_remote_answer_contract("compare ces deux strategies de cache")
    assert "missing_referent" in c["risk_flags"]


def test_contract_no_task_id_in_decision():
    c1 = build_remote_answer_contract("implemente une fonction python")
    c2 = build_remote_answer_contract("implemente une classe python")
    assert c1["answer_kind"] == c2["answer_kind"] == "code_file"
    assert c1["max_tokens"] == c2["max_tokens"] == 620


# ── balanced_compact_v3 — classification + live prompts ──────────────────────

def test_live_open_reasoning_classified_as_comparison():
    """Prompt live exact -> comparison (pas structured_summary)."""
    c = build_remote_answer_contract(
        "Compare microservices and monolithic architectures for a real-time payment system. "
        "Give the main trade-offs."
    )
    assert c["answer_kind"] == "comparison", (
        f"Expected 'comparison', got '{c['answer_kind']}'"
    )
    assert c["max_tokens"] == 420


def test_live_code_open_contract():
    """Prompt live exact code -> code_file, max_tokens=620, prompt ultra-court."""
    c = build_remote_answer_contract(
        "Write a Python function that validates and normalizes an email address, "
        "with simple tests."
    )
    assert c["answer_kind"] == "code_file"
    assert c["max_tokens"] == 620
    assert c["code_only"] is True
    assert len(c["contract_prompt"]) <= 160, (
        f"contract_prompt trop long: {len(c['contract_prompt'])} chars"
    )


# ── balanced_compact_v3 — contract prompt content ────────────────────────────

def test_code_prompt_no_prose_no_docstring():
    """Le contract_prompt code contient 'No prose' et 'no docstring'."""
    p = build_contract_prompt("code_file", False, True, "en", 130)
    assert "No prose" in p or "no prose" in p.lower()
    assert "no docstring" in p.lower()


def test_code_prompt_simple_asserts_no_try_except():
    """v3g: contract_prompt code contient 'simple asserts only' et 'No try/except'."""
    p = build_contract_prompt("code_file", False, True, "en", 130)
    assert "simple asserts only" in p
    assert "No try/except" in p


def test_code_prompt_no_unittest_main_no_main_guard():
    """Le contract_prompt code ne contient pas les clauses bannies."""
    p = build_contract_prompt("code_file", False, True, "en", 130)
    assert "__main__" not in p
    assert "unittest.main" not in p
    assert "standard-library implementation" not in p


def test_code_prompt_no_unittest_no_main():
    """v3g: contract_prompt code ne contient pas 'unittest' ni '__main__'."""
    p = build_contract_prompt("code_file", False, True, "en", 130)
    assert "unittest" not in p
    assert "__main__" not in p


def test_code_prompt_length():
    """Le contract_prompt code doit tenir en <= 160 chars."""
    p = build_contract_prompt("code_file", False, True, "en", 130)
    assert len(p) <= 160, f"contract_prompt code trop long: {len(p)} chars"


def test_prose_prompt_final_only():
    """v3f: contract_prompt prose commence par 'Final only'."""
    for kind in ("comparison", "structured_summary", "direct_answer"):
        p = build_contract_prompt(kind, False, False, "en", 60)
        assert p.startswith("Final only"), f"Missing 'Final only' for {kind}: {p!r}"


def test_prose_prompt_comparison_generic_labels():
    """Comparison keeps generic non-domain-specific labels."""
    prompt = build_contract_prompt(
        "comparison", False, False, "en", 60
    )

    assert (
        "Plain labels: A:, B:, Trade-offs:, Recommendation:."
        in prompt
    )


def test_prose_prompt_no_domain_specific_labels():
    """v3g2: aucun label métier hardcodé (anti-overfit hidden tasks)."""
    for kind in ("comparison", "structured_summary", "direct_answer"):
        p = build_contract_prompt(kind, False, False, "en", 60)
        assert "Monolith:" not in p
        assert "Microservices:" not in p


def test_prose_prompt_summary_direct_plain_text():
    """v3g2: structured_summary/direct_answer = moule texte générique sans labels."""
    for kind in ("structured_summary", "direct_answer"):
        p = build_contract_prompt(kind, False, False, "en", 60)
        assert "Plain text" in p
        assert "Keep brief" in p
        assert "Option A:" not in p
        assert "Option B:" not in p
        assert "Trade-off:" not in p


def test_prose_prompt_comparison_has_unambiguous_shape():
    prompt = build_contract_prompt(
        "comparison", False, False, "en", 60
    )

    assert "Trade-offs:" in prompt
    assert "Recommendation:" in prompt
    assert "One short sentence per label" not in prompt


def test_prose_prompt_no_title():
    """v3f: contract_prompt prose contient 'No title'."""
    p = build_contract_prompt("comparison", False, False, "en", 60)
    assert "No title" in p or "no title" in p.lower()


def test_prose_prompt_no_table_clause():
    """v3f: contract_prompt prose contient 'table' (interdit)."""
    p = build_contract_prompt("comparison", False, False, "en", 60)
    assert "table" in p.lower()


def test_prose_prompt_no_markdown_clause():
    """v3f: contract_prompt prose contient 'markdown' (interdit)."""
    p = build_contract_prompt("comparison", False, False, "en", 60)
    assert "markdown" in p.lower()


def test_prose_prompt_no_preamble():
    """v3f: contract_prompt prose contient 'preamble' (interdit)."""
    p = build_contract_prompt("comparison", False, False, "en", 60)
    assert "preamble" in p.lower()


def test_prose_prompt_no_analysis_clause():
    """v3f: contract_prompt prose contient 'analysis' (interdit)."""
    p = build_contract_prompt("comparison", False, False, "en", 60)
    assert "analysis" in p.lower()


def test_prose_prompt_no_quantitative_triggers():
    """v3f: contract_prompt prose ne contient aucun déclencheur de comptage."""
    p = build_contract_prompt("comparison", False, False, "en", 60)
    for forbidden in ("exactly", "under", "words", "lines", "count", "<="):
        assert forbidden not in p.lower(), f"Prompt contient déclencheur interdit: {forbidden!r}"
    # pas de chiffres isolés
    import re as _re
    assert not _re.search(r'\b\d+\b', p), f"Prompt contient un chiffre: {p!r}"


def test_prose_prompt_ultra_short():
    """Le contract_prompt prose comparison (sans referent) doit tenir en <= 170 chars."""
    p = build_contract_prompt("comparison", False, False, "en", 60)
    assert len(p) <= 170, f"contract_prompt prose trop long: {len(p)} chars"


def test_budget_balanced_compact_v3():
    """Vérification globale des budgets balanced_compact_v3."""
    assert select_max_tokens("comparison") == 420
    assert select_max_tokens("structured_summary") == 420
    assert select_max_tokens("code_file") == 620
    assert select_max_tokens("direct_answer") == 320
    assert select_max_tokens("clarification") == 80
