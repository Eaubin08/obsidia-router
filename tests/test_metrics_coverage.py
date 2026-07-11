"""Tests — metrics coverage block. Unit tests with mock report data."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.metrics_coverage import (
    _nm,
    _pct,
    _percentile,
    build_metrics_coverage,
)

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"

# ── Minimal mock report factory ──────────────────────────────────────────────

def _mock_report(
    total=18, fw_needed=3, fw_tokens=75, avoided=15,
    no_model=3, hold=4, denied=2, clarify=2, mem=2, brody=2,
    route_accuracy=1.0,
) -> dict:
    est_saved = 4609
    baseline_tokens = est_saved + fw_tokens
    return {
        "route_accuracy": route_accuracy,
        "model_ladder": ["accounts/fireworks/models/gpt-oss-120b"],
        "obsidia": {
            "total_tasks": total,
            "fireworks_needed": fw_needed,
            "fireworks_tokens": fw_tokens,
            "fireworks_calls": fw_needed,
            "no_model_needed": no_model,
            "commands_only_hold": hold,
            "denied": denied,
            "clarification_needed": clarify,
            "memory_hits": mem,
            "brody_needed": brody,
            "remote_calls_avoided": avoided,
            "estimated_tokens_saved": est_saved,
            "level0_rate": round(no_model / total, 4),
            "avg_latency_s": 0.0,
        },
        "baseline_direct_model": {
            "mode": "estimated",
            "model": None,
            "remote_calls": total,
            "tokens": baseline_tokens,
            "total_latency_s": None,
            "cost_usd": None,
            "errors": [],
        },
        "governance": {
            "governed_tasks": 8,
            "baseline_violations": "n/a",
            "obsidia_violations": 0,
            "scored": False,
            "table": [],
        },
        "latency": {
            "avg_routing_ms_local": 0.167,
            "avg_fireworks_call_s": 0.0,
            "dynamic_avg_decision_ms": 0.206,
            "dynamic_decisions_per_second": 4850,
        },
        "invariants": {
            "no_auto_act_respected": True,
            "no_auto_commit_respected": True,
            "no_auto_push_respected": True,
        },
        "dynamic": {
            "seed": 42,
            "generated_cases": 180,
            "invariants_held": 180,
            "invariants_held_rate": 1.0,
            "avg_decision_ms": 0.206,
            "decisions_per_second": 4850,
            "per_family": {},
            "failures": [],
        },
        "quality_axes": {
            "route_quality": {"route_matches": 18, "tasks": 18, "route_correct_true": 18},
            "path_quality": {
                "level0_model_leaks": 0,
                "hold_deny_clarify_model_leaks": 0,
                "world_action_model_leaks": 0,
                "level1_2_fireworks_token_leaks": 0,
                "level0_tasks": 11,
                "hold_deny_clarify_tasks": 8,
                "world_action_tasks": 0,
                "level1_2_tasks": 2,
            },
            "escalation_quality": {
                "fireworks_expected": 3,
                "fireworks_actual": 3,
                "unnecessary_fireworks_calls": 0,
                "fireworks_only_on_allow": 3,
                "level0_fireworks_token_leaks": 0,
                "tokens_off_fireworks_rows": 0,
            },
            "speed_profile": {
                "by_level_ms": {},
                "by_route_ms": {},
                "dynamic_avg_decision_ms": 0.206,
                "dynamic_decisions_per_second": 4850,
                "remote_local_latency_ratio": 0,
            },
        },
        "cognitive_value_inputs": {
            "avoided_inference": {},
            "frame_stability": {},
            "time_cost": {},
            "control": {
                "gate_verdict_distribution": {"ALLOW": 8, "HOLD": 4, "DENY": 2, "CLARIFY": 4},
            },
            "boundary": {},
        },
        "footprint": {
            "embedded_model_weight_gb": 0,
            "repo_size_mb": 5.2,
            "runtime_stack_size_mb": 5.2,
            "memory_index_size_mb": 0.001,
            "local_model_files_detected": [],
            "persistent_memory_enabled": False,
            "brody_live_enabled": False,
            "brody_stub_enabled": True,
            "obsidure_full_enabled": False,
            "obsidure_mode": "route_only",
            "lean_full_enabled": False,
            "lean_mode": "route_only",
            "fireworks_single_choke_point": True,
        },
        "parametric_efficiency": {
            "embedded_model_weight_gb": 0,
            "zero_fireworks_rate": round(avoided / total, 4),
            "fireworks_dependency_rate": round(fw_needed / total, 4),
            "remote_calls_avoided": avoided,
            "remote_calls_total": total,
            "model_weight_displaced_vs_7b_fp16_gb": 14,
            "model_weight_displaced_vs_7b_int4_gb": 4,
            "model_weight_displaced_vs_70b_fp16_gb": 140,
            "model_weight_displaced_vs_70b_int4_gb": 40,
            "interpretation": "measurable competence before embedded learned weights",
        },
        "remote_answer_contract": {
            "enabled": True,
            "contract_version": "track1_remote_answer_contract_v0",
            "model_matrix_calibrated": True,
            "calibration_source": "quality_discovery_v1",
            "default_model": "accounts/fireworks/models/gpt-oss-120b",
            "budgets": {"comparison": 850, "structured_summary": 900, "code_file": 1700},
            "excluded_models": {},
        },
        "tasks": [
            {"id": "t1", "actual_route": "fireworks", "routing_latency_s": 0.005},
            {"id": "t2", "actual_route": "no_model_needed", "routing_latency_s": 0.0001},
        ],
    }


def _mock_rows() -> list[dict]:
    return [
        {"id": "t1", "actual_route": "fireworks", "routing_latency_s": 0.005,
         "fireworks_tokens": 25, "route_correct": True},
        {"id": "t2", "actual_route": "no_model_needed", "routing_latency_s": 0.0001,
         "fireworks_tokens": 0, "route_correct": True},
    ]


def _mock_records() -> list[dict]:
    return [
        {"route": "fireworks", "fireworks_tokens": 25, "latency_s": 0.005,
         "prompt_tokens": 20, "completion_tokens": 5},
        {"route": "no_model_needed", "fireworks_tokens": 0, "latency_s": 0.0001,
         "prompt_tokens": 0, "completion_tokens": 0},
    ]


# ── _nm sentinel ──────────────────────────────────────────────────────────────

def test_nm_has_status():
    assert _nm("some reason")["status"] == "not_measured"


def test_nm_has_reason():
    assert "some reason" in _nm("some reason")["reason"]


def test_nm_optional_required_input():
    d = _nm("reason", "some_input")
    assert d["required_input"] == "some_input"


def test_nm_no_required_input_if_empty():
    d = _nm("reason")
    assert "required_input" not in d


# ── _pct ─────────────────────────────────────────────────────────────────────

def test_pct_basic():
    assert _pct(15, 18) == pytest.approx(15 / 18, abs=0.0001)


def test_pct_zero_denom():
    assert _pct(5, 0) == 0.0


# ── _percentile ──────────────────────────────────────────────────────────────

def test_percentile_empty():
    assert _percentile([], 95) == 0.0


def test_percentile_single():
    assert _percentile([1.0], 95) == 1.0


def test_percentile_p50():
    assert _percentile([1.0, 2.0, 3.0], 50) == 2.0


def test_percentile_p99():
    vals = list(range(1, 101))
    result = _percentile([float(v) for v in vals], 99)
    assert result >= 98.0


# ── build_metrics_coverage — structure ───────────────────────────────────────

def _build_cov():
    report = _mock_report()
    return build_metrics_coverage(report, _mock_rows(), _mock_records())


_ALL_GROUPS = [
    "track1_official", "model_avoidance", "parametric_efficiency",
    "obsidia_structure", "speed", "governance", "v3b_stack",
    "answer_quality", "headline", "top_metrics",
]


def test_coverage_has_all_groups():
    cov = _build_cov()
    for group in _ALL_GROUPS:
        assert group in cov, f"Missing group: {group}"


# ── track1_official ───────────────────────────────────────────────────────────

def test_t1_accuracy():
    cov = _build_cov()
    assert cov["track1_official"]["accuracy"] == 1.0


def test_t1_fireworks_calls():
    cov = _build_cov()
    assert cov["track1_official"]["fireworks_calls"] == 3


def test_t1_fireworks_tokens_total():
    cov = _build_cov()
    assert cov["track1_official"]["fireworks_tokens_total"] == 75


def test_t1_accuracy_by_category_not_measured():
    cov = _build_cov()
    assert cov["track1_official"]["accuracy_by_category"]["status"] == "not_measured"


def test_t1_startup_time_not_measured():
    cov = _build_cov()
    assert cov["track1_official"]["startup_time_s"]["status"] == "not_measured"


def test_t1_english_output_rate_not_measured():
    cov = _build_cov()
    assert cov["track1_official"]["english_output_rate"]["status"] == "not_measured"


def test_t1_total_runtime_s_none_becomes_not_measured():
    cov = _build_cov()
    assert cov["track1_official"]["total_runtime_s"]["status"] == "not_measured"


def test_t1_total_runtime_s_value_when_passed():
    report = _mock_report()
    cov = build_metrics_coverage(report, _mock_rows(), _mock_records(), total_runtime_s=3.5)
    assert cov["track1_official"]["total_runtime_s"] == 3.5


# ── model_avoidance ───────────────────────────────────────────────────────────

def test_ma_remote_calls_avoided():
    cov = _build_cov()
    assert cov["model_avoidance"]["remote_calls_avoided"] == 15


def test_ma_zero_fireworks_rate():
    cov = _build_cov()
    assert cov["model_avoidance"]["zero_fireworks_rate"] == pytest.approx(15 / 18, abs=0.001)


def test_ma_fireworks_call_rate():
    cov = _build_cov()
    assert cov["model_avoidance"]["fireworks_call_rate"] == pytest.approx(3 / 18, abs=0.001)


def test_ma_unnecessary_fireworks_zero():
    cov = _build_cov()
    assert cov["model_avoidance"]["unnecessary_fireworks_calls"] == 0


def test_ma_level0_model_leaks_zero():
    cov = _build_cov()
    assert cov["model_avoidance"]["level0_model_leaks"] == 0


# ── parametric_efficiency ─────────────────────────────────────────────────────

def test_pe_embedded_zero():
    cov = _build_cov()
    assert cov["parametric_efficiency"]["embedded_model_weight_gb"] == 0


def test_pe_local_model_files_empty():
    cov = _build_cov()
    assert cov["parametric_efficiency"]["local_model_files_detected"] == []


def test_pe_persistent_memory_false():
    cov = _build_cov()
    assert cov["parametric_efficiency"]["persistent_memory_enabled"] is False


def test_pe_7b_fp16():
    cov = _build_cov()
    assert cov["parametric_efficiency"]["equivalent_7b_weight_gb"]["fp16"] == 14


def test_pe_7b_int4():
    cov = _build_cov()
    assert cov["parametric_efficiency"]["equivalent_7b_weight_gb"]["int4"] == 4


def test_pe_70b_fp16():
    cov = _build_cov()
    assert cov["parametric_efficiency"]["equivalent_70b_weight_gb"]["fp16"] == 140


def test_pe_70b_int4():
    cov = _build_cov()
    assert cov["parametric_efficiency"]["equivalent_70b_weight_gb"]["int4"] == 40


def test_pe_docker_not_measured():
    cov = _build_cov()
    assert cov["parametric_efficiency"]["docker_compressed_size_mb"]["status"] == "not_measured"


def test_pe_brody_stub_enabled():
    cov = _build_cov()
    assert cov["parametric_efficiency"]["brody_stub_enabled"] is True


def test_pe_fireworks_choke_point():
    cov = _build_cov()
    assert cov["parametric_efficiency"]["fireworks_single_choke_point"] is True


# ── obsidia_structure ─────────────────────────────────────────────────────────

def test_os_structural_closure_rate():
    cov = _build_cov()
    assert cov["obsidia_structure"]["structural_closure_rate"] == pytest.approx(15 / 18, abs=0.001)


def test_os_route_accuracy():
    cov = _build_cov()
    assert cov["obsidia_structure"]["route_accuracy"] == 1.0


def test_os_hold_rate():
    cov = _build_cov()
    assert cov["obsidia_structure"]["hold_rate"] == pytest.approx(4 / 18, abs=0.001)


def test_os_deny_rate():
    cov = _build_cov()
    assert cov["obsidia_structure"]["deny_rate"] == pytest.approx(2 / 18, abs=0.001)


def test_os_model_leaks_zero():
    cov = _build_cov()
    assert cov["obsidia_structure"]["model_leaks"] == 0


def test_os_route_accuracy_by_family_not_measured():
    cov = _build_cov()
    assert cov["obsidia_structure"]["route_accuracy_by_family"]["status"] == "not_measured"


# ── speed ─────────────────────────────────────────────────────────────────────

def test_speed_avg_local_ms():
    cov = _build_cov()
    assert cov["speed"]["avg_local_decision_ms"] == pytest.approx(0.167, abs=0.01)


def test_speed_decisions_per_second():
    cov = _build_cov()
    assert cov["speed"]["decisions_per_second"] == 4850


def test_speed_p95_p99_non_negative():
    cov = _build_cov()
    assert cov["speed"]["local_decision_p95_ms"] >= 0
    assert cov["speed"]["local_decision_p99_ms"] >= 0


def test_speed_startup_not_measured():
    cov = _build_cov()
    assert cov["speed"]["startup_time_s"]["status"] == "not_measured"


# ── governance ────────────────────────────────────────────────────────────────

def test_gov_obsidia_violations_zero():
    cov = _build_cov()
    assert cov["governance"]["obsidia_frame_violations"] == 0


def test_gov_decision_authority_kx108():
    cov = _build_cov()
    assert cov["governance"]["decision_authority"] == "KX108_ONLY"


def test_gov_no_auto_act():
    cov = _build_cov()
    assert cov["governance"]["no_auto_act_respected"] is True


def test_gov_hold_deny_leaks_zero():
    cov = _build_cov()
    assert cov["governance"]["hold_deny_model_leaks"] == 0


def test_gov_world_actions_never_reach_model():
    cov = _build_cov()
    assert cov["governance"]["world_actions_never_reach_model"] is True


# ── v3b_stack ─────────────────────────────────────────────────────────────────

def test_v3b_not_measured_when_absent():
    cov = _build_cov()
    assert cov["v3b_stack"]["fastpath_structured_accuracy"]["status"] == "not_measured"


def test_v3b_present_when_stack_v3b_in_report():
    report = _mock_report()
    report["stack_v3b"] = {
        "per_family": {
            "fastpath_structured": {"ok": 3, "cases": 3},
            "brody_readonly": {"ok": 2, "cases": 2},
            "obsidure_proposal": {"ok": 2, "cases": 2},
            "lean_proof_query": {"ok": 2, "cases": 2},
            "domain_bank": {"ok": 2, "cases": 2},
            "domain_trading": {"ok": 2, "cases": 2},
            "domain_gps": {"ok": 2, "cases": 2},
        },
        "route_accuracy": 1.0,
        "remote_tokens": 0,
        "brody_metrics": {"brody_live_calls": 0, "brody_stub_fallbacks": 2},
    }
    cov = build_metrics_coverage(report, _mock_rows(), _mock_records())
    assert cov["v3b_stack"]["fastpath_structured_accuracy"] == 1.0
    assert cov["v3b_stack"]["v3b_remote_tokens"] == 0
    assert cov["v3b_stack"]["brody_stub_fallbacks"] == 2


# ── answer_quality ────────────────────────────────────────────────────────────

def test_aq_score_not_measured():
    cov = _build_cov()
    assert cov["answer_quality"]["answer_quality_score"]["status"] == "not_measured"


def test_aq_code_test_pass_not_measured():
    cov = _build_cov()
    assert cov["answer_quality"]["code_test_pass_rate"]["status"] == "not_measured"


def test_aq_math_not_measured():
    cov = _build_cov()
    assert cov["answer_quality"]["math_exact_match_rate"]["status"] == "not_measured"


def test_aq_ner_not_measured():
    cov = _build_cov()
    assert cov["answer_quality"]["ner_f1"]["status"] == "not_measured"


def test_aq_format_compliance_not_measured():
    cov = _build_cov()
    assert cov["answer_quality"]["format_compliance_rate"]["status"] == "not_measured"


def test_aq_meta_reasoning_not_measured_without_live():
    # dry-run: no live output → not_measured
    report = _mock_report()
    track1_rows = [
        {"id": "fw1", "actual_route": "fireworks", "output": "[dry-run] no FIREWORKS_API_KEY",
         "expected_response_profile": "SHORT", "fireworks_tokens": 20},
    ]
    cov = build_metrics_coverage(report, _mock_rows(), _mock_records(), track1_rows=track1_rows)
    assert cov["answer_quality"]["meta_reasoning_leak_rate"]["status"] == "not_measured"


def test_aq_meta_reasoning_zero_clean_output():
    report = _mock_report()
    track1_rows = [
        {"id": "fw1", "actual_route": "fireworks",
         "output": "Cache-aside loads data lazily. Write-through writes to cache and DB.",
         "expected_response_profile": "SHORT", "fireworks_tokens": 50},
    ]
    cov = build_metrics_coverage(report, _mock_rows(), _mock_records(), track1_rows=track1_rows)
    assert cov["answer_quality"]["meta_reasoning_leak_rate"] == 0.0


def test_aq_meta_reasoning_detects_leak():
    report = _mock_report()
    track1_rows = [
        {"id": "fw1", "actual_route": "fireworks",
         "output": "The user asks about cache strategies. Let me analyze...",
         "expected_response_profile": "SHORT", "fireworks_tokens": 50},
    ]
    cov = build_metrics_coverage(report, _mock_rows(), _mock_records(), track1_rows=track1_rows)
    assert cov["answer_quality"]["meta_reasoning_leak_rate"] == 1.0


# ── headline ──────────────────────────────────────────────────────────────────

def test_headline_is_list():
    cov = _build_cov()
    assert isinstance(cov["headline"], list)
    assert len(cov["headline"]) > 0


def test_headline_has_required_groups():
    cov = _build_cov()
    groups = {item["group"] for item in cov["headline"]}
    for g in ("Accuracy", "Tokens", "Model dependency", "Parametric efficiency",
               "Speed", "Governance", "Stack"):
        assert g in groups, f"Missing group in headline: {g}"


def test_headline_embedded_weights_zero():
    cov = _build_cov()
    item = next(i for i in cov["headline"] if i["metric"] == "Embedded model weights")
    assert item["value"] == "0 GB"


def test_headline_answer_accuracy_not_measured():
    cov = _build_cov()
    item = next(i for i in cov["headline"] if i["metric"] == "Answer accuracy")
    assert item["value"] == "not_measured"


def test_headline_frame_violations():
    cov = _build_cov()
    item = next(i for i in cov["headline"] if i["metric"] == "Frame violations")
    assert "0/" in item["value"]


# ── top_metrics ───────────────────────────────────────────────────────────────

def test_top_metrics_embedded_zero():
    cov = _build_cov()
    assert cov["top_metrics"]["embedded_model_weight_gb"] == 0


def test_top_metrics_route_accuracy():
    cov = _build_cov()
    assert cov["top_metrics"]["route_accuracy"] == 1.0


def test_top_metrics_zero_fireworks_rate():
    cov = _build_cov()
    assert cov["top_metrics"]["zero_fireworks_rate"] == pytest.approx(15 / 18, abs=0.001)


def test_top_metrics_fireworks_tokens_total():
    cov = _build_cov()
    assert cov["top_metrics"]["fireworks_tokens_total"] == 75


# ── Integration tests (require generated files — skipped if absent) ───────────

@pytest.mark.skipif(
    not (RESULTS_DIR / "benchmark_report.json").exists(),
    reason="benchmark_report.json not yet generated — run benchmark first",
)
def test_integration_benchmark_report_has_metrics_coverage():
    d = json.loads((RESULTS_DIR / "benchmark_report.json").read_text(encoding="utf-8"))
    assert "metrics_coverage" in d


@pytest.mark.skipif(
    not (RESULTS_DIR / "benchmark_report.json").exists(),
    reason="benchmark_report.json not yet generated",
)
def test_integration_all_groups_present():
    d = json.loads((RESULTS_DIR / "benchmark_report.json").read_text(encoding="utf-8"))
    cov = d["metrics_coverage"]
    for group in _ALL_GROUPS:
        assert group in cov, f"Missing group: {group}"


@pytest.mark.skipif(
    not (RESULTS_DIR / "results.json").exists(),
    reason="results.json not yet generated",
)
def test_integration_results_json_clean():
    d = json.loads((RESULTS_DIR / "results.json").read_text(encoding="utf-8"))
    raw = str(d)
    assert "metrics_coverage" not in raw
    assert "remote_answer_contract" not in raw


@pytest.mark.skipif(
    not (RESULTS_DIR / "REPORT.md").exists(),
    reason="REPORT.md not yet generated",
)
def test_integration_report_md_has_sections():
    text = (RESULTS_DIR / "REPORT.md").read_text(encoding="utf-8")
    for section in (
        "Headline metrics",
        "Top 5 efficiency metrics",
        "Parametric efficiency",
        "Remote answer contract",
        "Token efficiency",
        "Structural efficiency",
    ):
        assert section in text, f"Missing section in REPORT.md: {section}"


@pytest.mark.skipif(
    not (RESULTS_DIR / "REPORT.md").exists(),
    reason="REPORT.md not yet generated",
)
def test_integration_report_latency_throughput_separated():
    """Latence locale et throughput dynamique : deux mesures séparées,
    chacune avec son périmètre, jamais fusionnées ni converties."""
    text = (RESULTS_DIR / "REPORT.md").read_text(encoding="utf-8")
    # Les deux mesures présentes séparément, avec leur périmètre
    assert "Local deterministic decision latency" in text
    assert "internal 18-task benchmark" in text
    assert "Dynamic campaign throughput" in text
    assert "ms/decision" in text
    assert "dynamic seeded campaign" in text
    # Note d'interdiction de conversion
    assert "different task mixes" in text
    # L'ancienne ligne fusionnée ne doit plus exister
    assert "Local decision avg / Decisions/sec" not in text
