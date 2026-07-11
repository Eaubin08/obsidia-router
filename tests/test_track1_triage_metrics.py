"""LOT E — adaptive model triage evidence: instrumentation, aggregates,
schema. No network calls anywhere in this file.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.metrics import triage_metrics
from app.metrics.collector import MetricsCollector
from app.router.decision import decide


# ── Helpers ────────────────────────────────────────────────────────────────────

_MOCK_RESULT = {
    "text": "answer",
    "model": "small",
    "total_tokens": 10,
    "prompt_tokens": 4,
    "completion_tokens": 6,
    "latency_s": 0.01,
    "dry_run": False,
}


def _fireworks_record(model="small", rung=0, ladder_size=3, contract_pref="small",
                       raw_chars=20, system_chars=30, intent_type="reasoning"):
    return {
        "route": "fireworks",
        "level": 3,
        "intent_type": intent_type,
        "model": model,
        "selected_model": model,
        "selected_rung": rung,
        "selection_reason": f"rung {rung} of {ladder_size}-model ladder",
        "ladder_size": ladder_size,
        "contract_model_preference": contract_pref,
        "actual_model_used": model,
        "raw_prompt_chars": raw_chars,
        "system_prompt_chars": system_chars,
        "compression_applied": False,
        "compressed_prompt_chars": None,
        "fireworks_tokens": 10,
        "remote_call_avoided": False,
    }


def _local_record(route="local_solver", intent_type="code_request"):
    return {
        "route": route,
        "level": 1,
        "intent_type": intent_type,
        "model": None,
        "selected_model": None,
        "selected_rung": None,
        "selection_reason": None,
        "ladder_size": None,
        "contract_model_preference": None,
        "actual_model_used": None,
        "raw_prompt_chars": None,
        "system_prompt_chars": None,
        "compression_applied": None,
        "compressed_prompt_chars": None,
        "fireworks_tokens": 0,
        "remote_call_avoided": True,
    }


# ── 1. selected_model no longer comes from contract["model_preference"] ───────

def test_selected_model_is_not_contract_model_preference():
    """The historical bug: build_receipts used to write
    selected_model = contract["model_preference"]. Prove the field now
    diverges from contract_model_preference whenever the router picked a
    different rung."""
    from benchmarks.track1_runner import build_receipts

    row = {
        "id": "t1", "request": "implement x", "actual_route": "fireworks",
        "route_correct": True, "gate_verdict": "ALLOW", "gate_matched": "action",
        "level": 3, "model": "medium", "intent_type": "code_request",
        "target_layer": "COMPUTE", "missing": [], "fireworks_tokens": 10,
        "remote_call_avoided": False, "routing_latency_ms": 1.0,
        "output": "code", "memory_entry": None, "topic_name": "general",
        "actual_model_used": "medium", "selected_rung": 1,
        "selection_reason": "rung 1 of 3-model ladder",
        "raw_prompt_chars": 40, "system_prompt_chars": 60,
        "remote_answer_contract": {
            "answer_kind": "code_file", "model_preference": "gpt-oss-120b",
            "model_matrix_calibrated": True, "calibration_source": "quality_discovery_v1",
            "budget_headroom_policy": "human_margin_high_v0",
        },
        "expected_response_profile": "CODE_FILE",
    }
    receipts = build_receipts([row])
    task = receipts["tasks"][0]
    assert task["selected_model"] == "medium"
    assert task["contract_model_preference"] == "gpt-oss-120b"
    assert task["selected_model"] != task["contract_model_preference"]


def test_selected_model_none_on_local_route():
    from benchmarks.track1_runner import build_receipts

    row = {
        "id": "t2", "request": "statut", "actual_route": "no_model_needed",
        "route_correct": True, "gate_verdict": "ALLOW", "gate_matched": None,
        "level": 0, "model": None, "intent_type": "status",
        "target_layer": "system", "missing": [], "fireworks_tokens": 0,
        "remote_call_avoided": True, "routing_latency_ms": 0.5,
        "output": "ok", "memory_entry": None, "topic_name": "general",
    }
    receipts = build_receipts([row])
    task = receipts["tasks"][0]
    assert task["selected_model"] is None


# ── 2. selected_model == actual_model_used == captured chat model ────────────

def test_decide_run_one_and_transport_agree(monkeypatch):
    from app.cli import run_one

    ladder = ["small", "medium", "gpt-oss-120b"]
    metrics = MetricsCollector()
    with patch("app.adapters.fireworks.chat", return_value=_MOCK_RESULT) as mock_chat:
        with patch("app.adapters.fireworks.allowed_models", return_value=ladder):
            decision = run_one("Implement a complex distributed cache with concurrency control.",
                                metrics, {})
    assert decision["route"] == "fireworks"
    assert decision["model"] == decision["actual_model_used"]
    captured_model = mock_chat.call_args[0][0]
    assert captured_model == decision["model"]
    rec = metrics.records[-1]
    assert rec["selected_model"] == decision["model"] == captured_model


# ── 3-4. selected_rung / selection_reason propagated ──────────────────────────

def test_selected_rung_and_reason_propagate_through_decide_and_record():
    ladder = ["small", "medium", "gpt-oss-120b"]
    d = decide("Implement a complex distributed cache with concurrency control.",
               model_ladder=ladder)
    assert d["route"] == "fireworks"
    assert d["selected_rung"] == 2
    assert "rung 2" in d["selection_reason"]

    metrics = MetricsCollector()
    metrics.record("Implement a complex distributed cache with concurrency control.", d)
    rec = metrics.records[-1]
    assert rec["selected_rung"] == 2
    assert rec["selection_reason"] == d["selection_reason"]


# ── 5-6. model / rung distributions ───────────────────────────────────────────

def test_model_call_distribution():
    records = [_fireworks_record("small"), _fireworks_record("small"),
               _fireworks_record("medium"), _local_record()]
    dist = triage_metrics.model_call_distribution(records)
    assert dist == {"small": 2, "medium": 1}


def test_model_rung_distribution():
    records = [_fireworks_record(rung=0), _fireworks_record(rung=0),
               _fireworks_record(rung=2), _local_record()]
    dist = triage_metrics.model_rung_distribution(records)
    assert dist == {"0": 2, "2": 1}


# ── 7. first/intermediate/last rung rates ─────────────────────────────────────

def test_rung_position_rates_three_model_ladder():
    records = [
        _fireworks_record(model="small", rung=0, ladder_size=3),
        _fireworks_record(model="medium", rung=1, ladder_size=3),
        _fireworks_record(model="120b", rung=2, ladder_size=3),
        _fireworks_record(model="120b", rung=2, ladder_size=3),
    ]
    rates = triage_metrics.rung_position_rates(records)
    assert rates["first_rung_call_rate"] == 0.25
    assert rates["intermediate_rung_call_rate"] == 0.25
    assert rates["last_rung_call_rate"] == 0.5
    assert rates["single_rung_call_rate"] == 0.0
    # exclusivity: rates sum to 1.0 (no double counting)
    total = (rates["single_rung_call_rate"] + rates["first_rung_call_rate"]
             + rates["intermediate_rung_call_rate"] + rates["last_rung_call_rate"])
    assert round(total, 4) == 1.0


# ── 8. higher_rung_calls_avoided ──────────────────────────────────────────────

def test_higher_rung_calls_avoided():
    records = [
        _fireworks_record(rung=0, ladder_size=3),
        _fireworks_record(rung=1, ladder_size=3),
        _fireworks_record(rung=2, ladder_size=3),
    ]
    result = triage_metrics.higher_rung_calls_avoided(records)
    assert result["higher_rung_calls_avoided"] == 2
    assert result["highest_rung_required_calls"] == 1


# ── 9. zero remote calls -> safe rates, no ZeroDivisionError ─────────────────

def test_zero_remote_calls_are_safe():
    records = [_local_record(), _local_record(route="no_model_needed")]
    summary = triage_metrics.triage_summary(records)
    assert summary["remote_model_calls"] == 0
    assert summary["model_call_distribution"] == {}
    assert summary["first_rung_call_rate"] == 0.0
    assert summary["last_rung_call_rate"] == 0.0
    assert summary["single_rung_call_rate"] == 0.0
    assert summary["higher_rung_calls_avoided"] == 0
    assert summary["average_selected_rung"] == 0.0


def test_summary_on_empty_records_is_safe():
    summary = triage_metrics.triage_summary([])
    assert summary["remote_model_calls"] == 0
    assert summary["code_tasks_total"] == 0
    assert summary["local_solver_hit_rate"] == 0.0


# ── 10. 1-model ladder: single == 100%, no double counting ───────────────────

def test_single_model_ladder_rate_is_exclusive():
    records = [_fireworks_record(model="only", rung=0, ladder_size=1),
               _fireworks_record(model="only", rung=0, ladder_size=1)]
    rates = triage_metrics.rung_position_rates(records)
    assert rates["single_rung_call_rate"] == 1.0
    assert rates["first_rung_call_rate"] == 0.0
    assert rates["last_rung_call_rate"] == 0.0
    assert rates["intermediate_rung_call_rate"] == 0.0


# ── 11-12. code_tasks_closed_locally / remote_code_calls ─────────────────────

def test_code_task_metrics_definitions():
    records = [
        _local_record(route="local_solver", intent_type="code_request"),
        _fireworks_record(intent_type="code_request"),
        _fireworks_record(intent_type="reasoning"),  # not a code task
        _local_record(route="no_model_needed", intent_type="status"),
    ]
    m = triage_metrics.code_task_metrics(records)
    assert m["code_tasks_total"] == 2
    assert m["code_tasks_closed_locally"] == 1
    assert m["code_solver_closures"] == 1
    assert m["remote_code_calls"] == 1
    assert m["remote_code_call_rate"] == 0.5
    assert m["local_solver_hits"] == 1  # only the code local_solver row


# ── 13-14. raw_prompt_chars / system_prompt_chars ─────────────────────────────

def test_prompt_size_metrics():
    records = [
        _fireworks_record(raw_chars=10, system_chars=20),
        _fireworks_record(raw_chars=30, system_chars=40),
        _local_record(),
    ]
    m = triage_metrics.prompt_size_metrics(records)
    assert m["total_raw_prompt_chars"] == 40
    assert m["average_raw_prompt_chars"] == 20.0
    assert m["max_raw_prompt_chars"] == 30
    assert m["total_system_prompt_chars"] == 60


# ── 15. metrics never store full prompt content ───────────────────────────────

def test_metrics_never_store_full_prompt_text():
    ladder = ["small", "medium", "gpt-oss-120b"]
    metrics = MetricsCollector()
    secret_marker = "UNIQUE_SENTINEL_PROMPT_TEXT_MUST_NOT_LEAK"
    request = f"Implement a complex distributed thing. {secret_marker}"
    with patch("app.adapters.fireworks.chat", return_value=_MOCK_RESULT):
        with patch("app.adapters.fireworks.allowed_models", return_value=ladder):
            from app.cli import run_one
            run_one(request, metrics, {})
    dumped = json.dumps(metrics.records)
    assert secret_marker not in dumped
    assert metrics.records[-1]["raw_prompt_chars"] == len(request)


# ── 16. official AMD schema (results.json) unchanged ──────────────────────────

_SPEC = importlib.util.spec_from_file_location(
    "run_official_module_metrics", ROOT / "scripts" / "run_official.py")
run_official = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(run_official)


def test_official_results_schema_unchanged_by_lot_e(monkeypatch):
    monkeypatch.setenv("ALLOWED_MODELS", "small,medium,gpt-oss-120b")
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    monkeypatch.delenv(
        "OBSIDIA_TRACK1_TRIAGE_RECEIPTS",
        raising=False,
    )
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        inp = tmp / "tasks.json"
        outp = tmp / "results.json"
        inp.write_text(json.dumps([
            {"task_id": "a", "prompt": "statut du systeme"},
            {"task_id": "b", "prompt": "Implement a complex distributed cache with concurrency control."},
        ]), encoding="utf-8")
        orig_argv = sys.argv
        try:
            sys.argv = ["run_official.py", "--input", str(inp), "--output", str(outp)]
            rc = run_official.main()
        finally:
            sys.argv = orig_argv
        assert rc == 0
        results = json.loads(outp.read_text(encoding="utf-8"))
        assert isinstance(results, list)
        for row in results:
            assert set(row.keys()) == {"task_id", "answer"}
        # The official path writes only the judged artifact.
        triage_path = tmp / "track1_triage_receipts.json"
        assert not triage_path.exists()
        assert {
            item.name
            for item in tmp.iterdir()
        } == {
            "tasks.json",
            "results.json",
        }


# ── 17. no network call anywhere in this module ───────────────────────────────

def test_no_network_call_marker(monkeypatch):
    """Sanity: every test above ran with FIREWORKS_API_KEY unset or chat()
    mocked. This test asserts the dry-run adapter never opens a socket when
    no key is configured — regardless of the developer's local environment."""
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    from app.adapters import fireworks
    import importlib
    importlib.reload(fireworks)  # force re-read of env after monkeypatch
    result = fireworks.chat("small", "hello")
    assert result["dry_run"] is True
