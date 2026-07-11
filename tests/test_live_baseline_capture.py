"""Tests LOT G2 — politique de capture baseline par modèle.

Vérifie:
  - Registry : modèle connu → plafond attendu, modèle inconnu → KeyError.
  - Séparation baseline / Obsidia : la baseline n'utilise plus answer_kind.
  - Appel baseline : fireworks.chat reçoit le plafond du modèle.
  - Télémétrie : champs obligatoires présents, clés interdites absentes.
  - Compatibilité : budgets Obsidia inchangés, métriques LOT F inchangées.
"""

import ast
from pathlib import Path

import pytest

from benchmarks.baseline_capture_policy import (
    BASELINE_MODEL_CAPTURE_POLICY,
    baseline_capture_max_tokens,
    capture_policy_metadata,
)
from benchmarks.track1_remote_answer_contract import (
    build_remote_answer_contract,
)

BASELINE_MODEL = "accounts/fireworks/models/gpt-oss-120b"
UNKNOWN_MODEL = "accounts/fireworks/models/does-not-exist"

# ── Registry ──────────────────────────────────────────────────────────────────

def test_baseline_model_registered():
    assert BASELINE_MODEL in BASELINE_MODEL_CAPTURE_POLICY


def test_baseline_model_cap_is_8192():
    assert baseline_capture_max_tokens(BASELINE_MODEL) == 8192


def test_unknown_model_raises_key_error():
    with pytest.raises(KeyError, match="not registered"):
        baseline_capture_max_tokens(UNKNOWN_MODEL)


def test_no_silent_fallback_to_512():
    with pytest.raises(KeyError):
        baseline_capture_max_tokens(UNKNOWN_MODEL)


def test_policy_version_present():
    meta = capture_policy_metadata(BASELINE_MODEL)
    assert meta["capture_policy_version"] == "model_capture_ceiling_v1"


def test_calibration_source_present():
    meta = capture_policy_metadata(BASELINE_MODEL)
    assert meta["capture_limit_source"]


def test_unknown_model_metadata_raises_key_error():
    with pytest.raises(KeyError):
        capture_policy_metadata(UNKNOWN_MODEL)


# ── Séparation baseline / Obsidia ────────────────────────────────────────────

def test_baseline_does_not_use_answer_kind_for_max_tokens():
    """Deux prompts de types différents reçoivent le même plafond baseline."""
    cap_comparison = baseline_capture_max_tokens(BASELINE_MODEL)
    cap_code = baseline_capture_max_tokens(BASELINE_MODEL)
    assert cap_comparison == cap_code == 8192


def test_obsidia_comparison_budget_unchanged():
    contract = build_remote_answer_contract(
        "Compare SQL vs NoSQL and derive trade-offs."
    )
    assert contract["answer_kind"] == "comparison"
    assert contract["max_tokens"] == 420


def test_obsidia_summary_budget_unchanged():
    contract = build_remote_answer_contract(
        "Génère un résumé structuré des tradeoffs entre consistency et availability."
    )
    assert contract["answer_kind"] == "structured_summary"
    assert contract["max_tokens"] == 420


def test_obsidia_code_budget_unchanged():
    contract = build_remote_answer_contract(
        "Implement a Python token bucket rate limiting function."
    )
    assert contract["answer_kind"] == "code_file"
    assert contract["max_tokens"] == 620


def test_obsidia_direct_answer_budget_unchanged():
    contract = build_remote_answer_contract("What is the system status?")
    assert contract["answer_kind"] == "direct_answer"
    assert contract["max_tokens"] == 320


def test_obsidia_clarification_budget_unchanged():
    from benchmarks.track1_remote_answer_contract import _BUDGETS
    assert _BUDGETS["clarification"] == 80


# ── Appel baseline dans run_benchmark.py ─────────────────────────────────────

def _parse_run_benchmark():
    source = Path("benchmarks/run_benchmark.py").read_text(encoding="utf-8")
    return ast.parse(source), source


def test_baseline_call_uses_model_based_cap():
    _, source = _parse_run_benchmark()
    assert "baseline_capture_max_tokens(baseline_model)" in source


def test_baseline_call_does_not_use_request_based_cap():
    _, source = _parse_run_benchmark()
    assert "_baseline_capture_max_tokens(" not in source


def test_unknown_model_blocked_before_network_call():
    with pytest.raises(KeyError, match="not registered"):
        baseline_capture_max_tokens(UNKNOWN_MODEL)


# ── Télémétrie ────────────────────────────────────────────────────────────────

def test_requested_max_tokens_equals_model_cap_in_telemetry():
    _, source = _parse_run_benchmark()
    assert "_baseline_max_tokens = baseline_capture_max_tokens(baseline_model)" in source


def test_telemetry_forbidden_keys_absent():
    _, source = _parse_run_benchmark()
    telemetry_section = source[
        source.index("_baseline_telemetry.append"):
        source.index("baseline_tokens += b[\"total_tokens\"]")
    ]
    for forbidden in (
        '"request"', '"prompt"', '"answer"', '"text"',
        '"content"', '"reasoning_content"', '"memory_entry"',
    ):
        assert forbidden not in telemetry_section, (
            f"Clé interdite {forbidden} trouvée dans la télémétrie"
        )


def test_telemetry_mandatory_fields_present():
    _, source = _parse_run_benchmark()
    telemetry_section = source[
        source.index("_baseline_telemetry.append"):
        source.index("baseline_tokens += b[\"total_tokens\"]")
    ]
    for required in (
        '"task_id"', '"answer_kind"', '"requested_max_tokens"',
        '"prompt_tokens"', '"completion_tokens"', '"total_tokens"',
        '"finish_reason"', '"final_content_present"',
        '"reasoning_content_present"', '"truncated"', '"error"',
        '"final_text_chars"', '"latency_s"', '"usage_available"',
        '"selected_model"', '"actual_model_used"',
    ):
        assert required in telemetry_section, (
            f"Champ obligatoire {required} absent de la télémétrie"
        )


def test_telemetry_capture_policy_fields_added():
    _, source = _parse_run_benchmark()
    telemetry_section = source[
        source.index("_baseline_telemetry.append"):
        source.index("baseline_tokens += b[\"total_tokens\"]")
    ]
    assert '"capture_policy_version"' in telemetry_section
    assert '"capture_limit_source"' in telemetry_section


# ── Rapport baseline_direct_model ────────────────────────────────────────────

def test_baseline_direct_model_has_capture_fields():
    _, source = _parse_run_benchmark()
    section = source[source.index('"baseline_direct_model"'):]
    assert '"capture_policy"' in section
    assert '"capture_max_tokens"' in section
    assert '"capture_model"' in section


def test_baseline_direct_model_error_fields_present():
    _, source = _parse_run_benchmark()
    assert '"error_count"' in source
    assert '"truncated_completion_count"' in source
    assert '"complete_response_count"' in source
    assert '"responses_with_reasoning_count"' in source
    assert '"responses_with_final_content_count"' in source


# ── Compatibilité LOT F ──────────────────────────────────────────────────────

def test_lot_f_telemetry_fields_unchanged():
    _, source = _parse_run_benchmark()
    assert "baseline_task_telemetry" in source
    assert "metadata_only_v0" in source


def test_route_metrics_unchanged():
    _, source = _parse_run_benchmark()
    assert '"exact_route_match"' in source
    assert '"accepted_route_correct"' in source
    assert '"alternative_route_used"' in source
    assert '"allowed_routes"' in source


def test_estimated_and_measured_tokens_separated():
    _, source = _parse_run_benchmark()
    assert '"estimated_tokens_saved_source"' in source
    assert '"measured_live_tokens_saved"' in source
    assert '"measured_live_tokens_available"' in source


def test_quality_labels_exact_and_accepted_routes():
    _, source = _parse_run_benchmark()
    assert "Exact route match:" in source
    assert "Accepted route accuracy" in source
    assert "Expected Fireworks route / actual remote calls:" in source
    assert "Alternative accepted routes used:" in source


def test_verified_local_closure_rate_in_answer_accuracy():
    source = Path("benchmarks/answer_accuracy.py").read_text(encoding="utf-8")
    assert '"verified_local_closure_rate": round(' in source
    assert '"verified_local_closure_rate_label"' in source
