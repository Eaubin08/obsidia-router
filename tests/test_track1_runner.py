"""Tests — Track 1 runner : answers courtes, results.json, receipts_internal.json."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from benchmarks.track1_runner import (
    build_receipts,
    build_results,
    track1_answer,
    write_track1,
)

# ── Fixtures de rows ──────────────────────────────────────────────────────────

def _row(
    route: str,
    ok: bool = True,
    tokens: int = 0,
    output: str = "",
    gate: str = "ALLOW",
    gate_matched: str | None = None,
    intent: str = "question",
    layer: str = "unknown",
    missing: list[str] | None = None,
    memory_entry: str | None = None,
    model: str | None = None,
    topic_name: str = "GENERAL",
    expected_response_profile: str | None = None,
) -> dict:
    return {
        "id": f"task_{route}",
        "request": "test request",
        "expected_route": route,
        "actual_route": route,
        "route_correct": ok,
        "gate_verdict": gate,
        "gate_matched": gate_matched,
        "level": 0 if route != "fireworks" else 3,
        "model": model,
        "intent_type": intent,
        "target_layer": layer,
        "missing": missing or [],
        "fireworks_tokens": tokens,
        "remote_call_avoided": route != "fireworks",
        "routing_latency_ms": 0.5,
        "output": output,
        "memory_entry": memory_entry,
        "topic_name": topic_name,
        "expected_response_profile": expected_response_profile,
    }


# ── track1_answer — pas de dump IR, pas de gouvernance interne ────────────────

def test_no_model_needed_returns_short_status():
    row = _row("no_model_needed", intent="status")
    ans = track1_answer(row)
    assert "System operational" in ans
    # Pas de dump IR
    assert "UnifiedInputIR" not in ans
    assert "intent_type" not in ans
    assert "target_layer" not in ans


def test_no_model_needed_non_status_no_ir_dump():
    row = _row("no_model_needed", intent="plan")
    ans = track1_answer(row)
    assert "UnifiedInputIR" not in ans
    assert len(ans) < 200


def test_hold_contains_matched_keyword():
    row = _row("hold_commands_only", gate_matched="push", gate="HOLD")
    ans = track1_answer(row)
    assert "push" in ans
    assert "HOLD" in ans
    assert "approval" in ans.lower()


def test_hold_no_governance_internals():
    row = _row("hold_commands_only", gate_matched="commit", gate="HOLD")
    ans = track1_answer(row)
    assert "KX108_ONLY" not in ans
    assert "real_action" not in ans
    assert "kernel_mutation" not in ans


def test_denied_contains_matched_keyword():
    row = _row("denied", gate_matched="rm -rf", gate="DENY")
    ans = track1_answer(row)
    assert "DENIED" in ans
    assert "rm -rf" in ans


def test_clarification_contains_missing():
    row = _row("clarification_needed", missing=["intent"], gate="CLARIFY")
    ans = track1_answer(row)
    assert "intent" in ans
    assert "Clarification" in ans or "clarification" in ans.lower()


def test_clarification_multiple_missing():
    row = _row("clarification_needed", missing=["intent", "target_scope"], gate="CLARIFY")
    ans = track1_answer(row)
    assert "intent" in ans
    assert "target_scope" in ans


def test_memory_hit_returns_content():
    mem = "Obsidia Router public cut — deterministic pre-inference layer."
    row = _row("memory_hit", memory_entry=mem)
    ans = track1_answer(row)
    assert ans == mem


def test_memory_hit_falls_back_to_output():
    row = _row("memory_hit", output="fallback output", memory_entry=None)
    ans = track1_answer(row)
    assert "fallback output" in ans or len(ans) > 0


def test_brody_stub_no_internal_text():
    """[brody-stub] ne doit pas apparaître dans la réponse Track 1."""
    stub_text = "[brody-stub] topic=REASONING intent=question layer=brody — bounded local answer."
    row = _row("brody", output=stub_text)
    ans = track1_answer(row)
    assert "[brody-stub]" not in ans
    assert len(ans) > 0


def test_brody_live_returns_real_output():
    """Si Brody est live, sa réponse réelle doit être retournée intacte."""
    live_text = "Brody est actif en mode readonly consultatif."
    row = _row("brody", output=live_text)
    ans = track1_answer(row)
    assert ans == live_text


def test_fireworks_returns_model_answer():
    model_ans = "The distributed cache should use consistent hashing with virtual nodes."
    row = _row("fireworks", output=model_ans, tokens=42,
               model="accounts/fireworks/models/gpt-oss-120b")
    ans = track1_answer(row)
    assert ans == model_ans


def test_fireworks_dry_run_output_passthrough():
    """En dry-run, le texte dry-run est retourné (pas transformé)."""
    row = _row("fireworks", output="[dry-run] no FIREWORKS_API_KEY — call not sent", tokens=0)
    ans = track1_answer(row)
    assert "[dry-run]" in ans


def test_obsidure_route_short():
    row = _row("obsidure_route_only")
    ans = track1_answer(row)
    assert "Obsidure" in ans
    assert len(ans) < 120


def test_lean_route_short():
    row = _row("lean_route_only")
    ans = track1_answer(row)
    assert "Lean" in ans or "proof" in ans.lower()


def test_domain_bridge_short():
    row = _row("domain_bridge", layer="domain")
    ans = track1_answer(row)
    assert "domain" in ans.lower() or "Domain" in ans


# ── build_results — format public ────────────────────────────────────────────

def _sample_rows() -> list[dict]:
    return [
        _row("no_model_needed", intent="status"),
        _row("hold_commands_only", gate_matched="push", gate="HOLD"),
        _row("denied", gate_matched="rm -rf", gate="DENY"),
        _row("clarification_needed", missing=["intent"], gate="CLARIFY"),
        _row("memory_hit", memory_entry="Project state: OK"),
        _row("brody", output="[brody-stub] topic=GENERAL"),
        _row("fireworks", tokens=42, output="Model answer here",
             model="accounts/fireworks/models/gpt-oss-120b"),
    ]


def test_results_has_all_required_fields():
    results = build_results(_sample_rows())
    assert "format_version" in results
    assert "total_tasks" in results
    assert "route_accuracy" in results
    assert "tokens_used_total" in results
    assert "tasks" in results
    for task in results["tasks"]:
        for field in ("id", "answer", "route", "level", "tokens_used",
                      "fireworks_model", "latency_ms", "route_correct"):
            assert field in task, f"champ manquant dans task: {field}"


def test_results_no_governance_fields_in_answer():
    """Les champs de gouvernance ne doivent PAS apparaître dans les answers."""
    results = build_results(_sample_rows())
    for task in results["tasks"]:
        ans = task["answer"]
        assert "KX108_ONLY" not in ans
        assert "real_action" not in ans
        assert "kernel_mutation" not in ans
        assert "memory_write" not in ans
        assert "emits_act" not in ans


def test_results_no_ir_dump_in_answer():
    """Les dumps IR ne doivent pas apparaître dans les answers."""
    results = build_results(_sample_rows())
    for task in results["tasks"]:
        ans = task["answer"]
        assert "UnifiedInputIR" not in ans
        assert "intent_type :" not in ans
        assert "target_layer:" not in ans


def test_results_no_brody_stub_in_answer():
    results = build_results(_sample_rows())
    for task in results["tasks"]:
        assert "[brody-stub]" not in task["answer"]


def test_results_token_count_correct():
    results = build_results(_sample_rows())
    assert results["tokens_used_total"] == 42
    fw_task = next(t for t in results["tasks"] if t["route"] == "fireworks")
    assert fw_task["tokens_used"] == 42


def test_results_route_accuracy():
    results = build_results(_sample_rows())
    # Tous les rows ont route_correct=True dans notre fixture
    assert results["route_accuracy"] == 1.0


def test_results_accuracy_partial():
    rows = [
        _row("no_model_needed", ok=True),
        _row("fireworks", ok=False, tokens=10, output="wrong"),
    ]
    results = build_results(rows)
    assert results["route_accuracy"] == 0.5


# ── build_receipts — gouvernance interne complète ────────────────────────────

def test_receipts_has_governance_block():
    receipts = build_receipts(_sample_rows())
    assert "governance" in receipts
    gov = receipts["governance"]
    assert gov["real_action"] is False
    assert gov["memory_write"] is False
    assert gov["kernel_mutation"] is False
    assert gov["emits_act"] is False
    assert gov["decision_authority"] == "KX108_ONLY"


def test_receipts_has_full_task_fields():
    receipts = build_receipts(_sample_rows())
    for task in receipts["tasks"]:
        for field in ("id", "request", "expected_route", "actual_route",
                      "route_correct", "gate_verdict", "gate_matched",
                      "level", "model", "intent_type", "target_layer",
                      "fireworks_tokens", "remote_call_avoided"):
            assert field in task, f"champ manquant dans receipt: {field}"


def test_receipts_contains_request_text():
    receipts = build_receipts(_sample_rows())
    for task in receipts["tasks"]:
        assert task["request"] == "test request"


# ── write_track1 — écriture fichiers ─────────────────────────────────────────

def test_write_track1_creates_both_files():
    rows = _sample_rows()
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        result = write_track1(rows, out_dir)
        assert result["results_path"].exists()
        assert result["receipts_path"].exists()


def test_write_track1_results_json_valid():
    rows = _sample_rows()
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        result = write_track1(rows, out_dir)
        data = json.loads(result["results_path"].read_text(encoding="utf-8"))
        assert data["total_tasks"] == len(rows)
        assert len(data["tasks"]) == len(rows)
        assert "format_version" in data


def test_write_track1_receipts_json_valid():
    rows = _sample_rows()
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        result = write_track1(rows, out_dir)
        data = json.loads(result["receipts_path"].read_text(encoding="utf-8"))
        assert data["governance"]["decision_authority"] == "KX108_ONLY"
        assert len(data["tasks"]) == len(rows)


def test_write_track1_receipts_not_in_results():
    """results.json ne doit PAS contenir les champs de gouvernance interne."""
    rows = _sample_rows()
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        result = write_track1(rows, out_dir)
        results_text = result["results_path"].read_text(encoding="utf-8")
        assert "KX108_ONLY" not in results_text
        assert "real_action" not in results_text
        assert "kernel_mutation" not in results_text
        # Les receipts, eux, doivent les contenir
        receipts_text = result["receipts_path"].read_text(encoding="utf-8")
        assert "KX108_ONLY" in receipts_text


def test_write_track1_summary_returned():
    rows = _sample_rows()
    with tempfile.TemporaryDirectory() as tmp:
        result = write_track1(rows, Path(tmp))
        assert result["total_tasks"] == len(rows)
        assert "route_accuracy" in result
        assert "tokens_used_total" in result
        assert "remote_calls" in result


# ── receipts — champs response profile telemetry ──────────────────────────────

def test_receipts_tasks_have_profile_telemetry_fields():
    """Chaque task dans receipts doit avoir les champs de profil de réponse borné + A3 labels."""
    rows = [
        _row("fireworks", tokens=42, output="A concise answer.",
             model="accounts/fireworks/models/gpt-oss-120b",
             expected_response_profile="SHORT"),
    ]
    receipts = build_receipts(rows)
    task = receipts["tasks"][0]
    required_profile_fields = {
        "expected_response_profile",
        "observed_response_size",
        "observed_answer_words",
        "density",
        "projection_cost",
        "compact_policy_source",
        "brody_policy_imported",
        # A3 audit labels
        "bounded_remote_call",
        "response_budget_profile",
        "response_budget_source",
        "response_budget_applied_before_generation",
    }
    assert required_profile_fields <= set(task.keys()), (
        f"Champs manquants dans receipt task: {required_profile_fields - set(task.keys())}"
    )


def test_receipts_brody_not_imported_flag():
    """brody_policy_imported doit être False (pas d'import privé)."""
    rows = [_row("fireworks", output="short answer", expected_response_profile="MEDIUM")]
    receipts = build_receipts(rows)
    assert receipts["tasks"][0]["brody_policy_imported"] is False


def test_receipts_compact_policy_source():
    rows = [_row("no_model_needed", intent="status", expected_response_profile="SHORT")]
    receipts = build_receipts(rows)
    assert receipts["tasks"][0]["compact_policy_source"] == "brody_like_track1_local"


def test_receipts_expected_profile_preserved():
    rows = [_row("fireworks", output="def foo(): pass", expected_response_profile="CODE")]
    receipts = build_receipts(rows)
    assert receipts["tasks"][0]["expected_response_profile"] == "CODE"


def test_results_json_has_no_profile_telemetry_fields():
    """results.json public ne doit PAS contenir les champs de telemetry profil."""
    rows = [
        _row("fireworks", tokens=42, output="answer",
             model="accounts/fireworks/models/gpt-oss-120b",
             expected_response_profile="SHORT"),
    ]
    results = build_results(rows)
    results_str = json.dumps(results)
    assert "compact_policy_source" not in results_str
    assert "brody_policy_imported" not in results_str
    assert "expected_response_profile" not in results_str
    assert "observed_response_size" not in results_str
    assert "projection_cost" not in results_str


def test_write_track1_receipts_has_profile_fields():
    """Vérifier que les champs profil sont bien dans receipts_internal.json sur disque."""
    rows = [
        _row("fireworks", tokens=42, output="fast answer",
             model="accounts/fireworks/models/gpt-oss-120b",
             expected_response_profile="SHORT"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        result = write_track1(rows, Path(tmp))
        receipts_data = json.loads(result["receipts_path"].read_text(encoding="utf-8"))
        task = receipts_data["tasks"][0]
        assert "expected_response_profile" in task
        assert "observed_answer_words" in task
        assert task["brody_policy_imported"] is False
        # A3 labels must be present on disk
        assert "bounded_remote_call" in task
        assert "response_budget_profile" in task
        assert "response_budget_source" in task
        assert "response_budget_applied_before_generation" in task


# ── A3 labels — distinction bounded vs avoided ────────────────────────────────

def test_receipts_fireworks_with_profile_is_bounded_remote():
    """Tâche fireworks avec expected_response_profile → bounded_remote_call=True."""
    rows = [
        _row("fireworks", tokens=42, output="answer",
             model="accounts/fireworks/models/gpt-oss-120b",
             expected_response_profile="SHORT"),
    ]
    receipts = build_receipts(rows)
    task = receipts["tasks"][0]
    assert task["bounded_remote_call"] is True
    assert task["response_budget_applied_before_generation"] is True


def test_receipts_non_fireworks_is_not_bounded_remote():
    """Tâche non-fireworks → bounded_remote_call=False (call avoided, not bounded)."""
    rows = [
        _row("no_model_needed", intent="status"),
        _row("hold_commands_only", gate_matched="push", gate="HOLD"),
        _row("memory_hit", memory_entry="Project state: OK"),
    ]
    receipts = build_receipts(rows)
    for task in receipts["tasks"]:
        assert task["bounded_remote_call"] is False, (
            f"Task {task['id']} route={task['actual_route']} "
            f"should not be bounded_remote_call"
        )
        assert task["response_budget_applied_before_generation"] is False


def test_receipts_fireworks_without_profile_is_not_bounded():
    """Tâche fireworks SANS expected_response_profile → bounded=False (pas de budget appliqué)."""
    rows = [
        _row("fireworks", tokens=10, output="answer",
             model="accounts/fireworks/models/gpt-oss-120b",
             expected_response_profile=None),
    ]
    receipts = build_receipts(rows)
    task = receipts["tasks"][0]
    assert task["bounded_remote_call"] is False


def test_receipts_brody_is_not_bounded_remote():
    """Tâche brody → bounded_remote_call=False (local organ, pas d'appel Fireworks)."""
    rows = [_row("brody", output="Brody advisory answer")]
    receipts = build_receipts(rows)
    assert receipts["tasks"][0]["bounded_remote_call"] is False


def test_results_json_no_a3_labels_leak():
    """Les 4 champs A3 ne doivent PAS apparaître dans results.json public."""
    rows = [
        _row("fireworks", tokens=42, output="answer",
             model="accounts/fireworks/models/gpt-oss-120b",
             expected_response_profile="SHORT"),
    ]
    results = build_results(rows)
    results_str = json.dumps(results)
    a3_fields = [
        "bounded_remote_call",
        "response_budget_profile",
        "response_budget_source",
        "response_budget_applied_before_generation",
    ]
    for field in a3_fields:
        assert field not in results_str, (
            f"A3 field {field!r} leaked into public results.json"
        )
