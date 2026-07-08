"""Tests — imported proof metrics: loader, mapper, report integration."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# ── Fake proof metrics fixture ────────────────────────────────────────────────

_FAKE_PROOF = {
    "run_meta": {
        "status_global": "PASS",
        "duration_total_s": 12.34,
        "commit_sha": "abc123",
        "runner": "scripts/run_all_proofs.ps1",
        "profile": "public_p1",
    },
    "phase_metrics": {
        "lean_build": {"status": "PASS", "duration_s": 1.2},
        "tlc_x108_mc": {
            "status": "PASS",
            "duration_s": 2.3,
            "states_generated": 100,
            "distinct_states": 80,
            "queue_left": 0,
        },
        "tlc_distributed_x108": {
            "status": "PASS",
            "duration_s": 3.1,
            "states_generated": 200,
            "distinct_states": 150,
            "queue_left": 0,
        },
        "verify_all": {"status": "PASS", "duration_s": 0.8},
        "verify_decision": {"status": "PASS", "duration_s": 0.5, "scenarios_checked": 12},
        "sigma_public": {"status": "PASS", "duration_s": 0.3},
        "sigma_tests": {
            "status": "PASS",
            "tests_total": 20,
            "tests_passed": 20,
            "tests_failed": 0,
            "slowest_tests": [],
        },
        "qa_anchor_schema": {"status": "PASS", "tests_total": 4, "tests_passed": 4},
    },
    "gps_semantics": {
        "summary": {
            "cases_total": 5,
            "cases_passed": 5,
            "allow_count": 1,
            "hold_count": 3,
            "block_count": 1,
            "mean_truth_score": 0.91,
            "mean_sigma_score": 0.72,
            "mean_mismatch_gap": 0.19,
        },
        "cases": [],
    },
    "safety_summary": {"status": "PASS"},
}


def _write_fake(tmp: Path) -> Path:
    p = tmp / "fake_proof_metrics.json"
    p.write_text(json.dumps(_FAKE_PROOF), encoding="utf-8")
    return p


def _run_benchmark(argv_extra: list[str], tmp: Path) -> tuple[int, Path]:
    tasks_path = tmp / "tasks.json"
    tasks_path.write_text(
        json.dumps([
            {"id": "t1", "request": "statut du systeme", "expected_route": "no_model_needed"},
        ]),
        encoding="utf-8",
    )
    out_dir = tmp / "out"
    orig = sys.argv
    try:
        sys.argv = [
            "run_benchmark.py",
            "--tasks-file", str(tasks_path),
            "--out-dir", str(out_dir),
        ] + argv_extra
        from benchmarks.run_benchmark import main
        rc = main()
    finally:
        sys.argv = orig
    return rc, out_dir


# ── 1. load_proof_metrics(None) returns {} ────────────────────────────────────

def test_load_none_returns_empty():
    from benchmarks.imported_proof_metrics import load_proof_metrics
    assert load_proof_metrics(None) == {}


# ── 2. missing explicit path raises FileNotFoundError ────────────────────────

def test_missing_explicit_path_raises():
    from benchmarks.imported_proof_metrics import load_proof_metrics
    with pytest.raises(FileNotFoundError, match="not found"):
        load_proof_metrics("/nonexistent/path/metrics.json")


# ── 3. invalid JSON raises ValueError ────────────────────────────────────────

def test_invalid_json_raises_value_error():
    from benchmarks.imported_proof_metrics import load_proof_metrics
    with tempfile.TemporaryDirectory() as tmp_str:
        bad = Path(tmp_str) / "bad.json"
        bad.write_text("{ not valid json !!!}", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_proof_metrics(bad)


# ── 4. build_imported_proof_metrics maps run_meta ────────────────────────────

def test_maps_run_meta():
    from benchmarks.imported_proof_metrics import build_imported_proof_metrics
    bloc = build_imported_proof_metrics(_FAKE_PROOF)
    assert bloc["enabled"] is True
    rm = bloc["run_meta"]
    assert rm["proof_status_global"] == "PASS"
    assert rm["proof_run_duration_total_s"] == 12.34
    assert rm["proof_commit_sha"] == "abc123"
    assert rm["proof_runner"] == "scripts/run_all_proofs.ps1"
    assert rm["proof_profile"] == "public_p1"


# ── 5. maps lean_build ───────────────────────────────────────────────────────

def test_maps_lean_build():
    from benchmarks.imported_proof_metrics import build_imported_proof_metrics
    bloc = build_imported_proof_metrics(_FAKE_PROOF)
    assert bloc["formal"]["lean_build_status"] == "PASS"
    assert bloc["formal"]["lean_build_duration_s"] == 1.2


# ── 6. maps tlc_x108 ────────────────────────────────────────────────────────

def test_maps_tlc_x108():
    from benchmarks.imported_proof_metrics import build_imported_proof_metrics
    bloc = build_imported_proof_metrics(_FAKE_PROOF)
    f = bloc["formal"]
    assert f["tlc_x108_status"] == "PASS"
    assert f["tlc_x108_states_generated"] == 100
    assert f["tlc_x108_distinct_states"] == 80
    assert f["tlc_x108_queue_left"] == 0


# ── 7. maps verify_decision ─────────────────────────────────────────────────

def test_maps_verify_decision():
    from benchmarks.imported_proof_metrics import build_imported_proof_metrics
    bloc = build_imported_proof_metrics(_FAKE_PROOF)
    v = bloc["verification"]
    assert v["verify_decision_status"] == "PASS"
    assert v["verify_decision_scenarios_checked"] == 12


# ── 8. maps sigma_tests ─────────────────────────────────────────────────────

def test_maps_sigma_tests():
    from benchmarks.imported_proof_metrics import build_imported_proof_metrics
    bloc = build_imported_proof_metrics(_FAKE_PROOF)
    s = bloc["sigma"]
    assert s["sigma_tests_total"] == 20
    assert s["sigma_tests_passed"] == 20
    assert s["sigma_tests_failed"] == 0


# ── 9. maps gps_semantics summary ───────────────────────────────────────────

def test_maps_gps_summary():
    from benchmarks.imported_proof_metrics import build_imported_proof_metrics
    bloc = build_imported_proof_metrics(_FAKE_PROOF)
    g = bloc["gps_semantics"]
    assert g["gps_cases_total"] == 5
    assert g["gps_cases_passed"] == 5
    assert g["gps_allow_count"] == 1
    assert g["gps_hold_count"] == 3
    assert g["gps_block_count"] == 1
    assert abs(g["gps_mean_mismatch_gap"] - 0.19) < 1e-6


# ── 10. maps anchor_schema ───────────────────────────────────────────────────

def test_maps_anchor_schema():
    from benchmarks.imported_proof_metrics import build_imported_proof_metrics
    bloc = build_imported_proof_metrics(_FAKE_PROOF)
    a = bloc["anchor_schema"]
    assert a["anchor_schema_tests_total"] == 4
    assert a["anchor_schema_tests_passed"] == 4
    assert a["qa_anchor_schema_status"] == "PASS"


# ── 11. missing nested fields become not_measured ────────────────────────────

def test_missing_nested_fields_become_not_measured():
    from benchmarks.imported_proof_metrics import build_imported_proof_metrics
    sparse = {"run_meta": {"status_global": "PASS"}}
    bloc = build_imported_proof_metrics(sparse)
    assert bloc["enabled"] is True
    assert bloc["formal"]["lean_build_status"] == "not_measured"
    assert bloc["verification"]["verify_decision_scenarios_checked"] == "not_measured"
    assert bloc["sigma"]["sigma_tests_total"] == "not_measured"


# ── 12. scored_track1 is always False ────────────────────────────────────────

def test_scored_track1_always_false():
    from benchmarks.imported_proof_metrics import build_imported_proof_metrics
    bloc_full = build_imported_proof_metrics(_FAKE_PROOF)
    bloc_empty = build_imported_proof_metrics(None)
    assert bloc_full["scored_track1"] is False
    assert bloc_empty["scored_track1"] is False


# ── 13. imported_proof_metrics absent from results.json public ───────────────

def test_imported_proof_metrics_absent_from_results_json():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        proof_path = _write_fake(tmp)
        rc, out_dir = _run_benchmark(
            ["--track1-official", "--no-receipts", "--proof-metrics-file", str(proof_path)],
            tmp,
        )
        results_path = out_dir / "results.json"
        assert results_path.exists()
        content = results_path.read_text(encoding="utf-8")
        assert "imported_proof_metrics" not in content


# ── 14. REPORT.md contains Proof benchmark metrics section ───────────────────

def test_report_md_contains_proof_section():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        proof_path = _write_fake(tmp)
        rc, out_dir = _run_benchmark(
            ["--proof-metrics-file", str(proof_path)],
            tmp,
        )
        md = (out_dir / "REPORT.md").read_text(encoding="utf-8")
        assert "Proof benchmark metrics" in md
        assert "not Track 1 scored" in md
        assert "imported read-only" in md


# ── 15. --proof-metrics-file injects enabled=true ────────────────────────────

def test_proof_metrics_file_flag_injects_enabled():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        proof_path = _write_fake(tmp)
        rc, out_dir = _run_benchmark(
            ["--proof-metrics-file", str(proof_path)],
            tmp,
        )
        report = json.loads((out_dir / "benchmark_report.json").read_text(encoding="utf-8"))
        pm = report.get("imported_proof_metrics", {})
        assert pm.get("enabled") is True
        assert pm.get("scored_track1") is False
        top = pm.get("top_proof_metrics", {})
        assert top.get("proof_status_global") == "PASS"
        assert top.get("lean_build_status") == "PASS"
        assert top.get("tlc_x108_states_generated") == 100
        assert top.get("verify_decision_scenarios_checked") == 12


# ── 16. no proof file → benchmark still passes, block is disabled ─────────────

def test_no_proof_file_benchmark_passes():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        rc, out_dir = _run_benchmark([], tmp)
        assert rc == 0
        report = json.loads((out_dir / "benchmark_report.json").read_text(encoding="utf-8"))
        pm = report.get("imported_proof_metrics", {})
        assert pm.get("enabled") is False
        assert pm.get("scored_track1") is False
        assert pm.get("status") == "not_measured"


# ── 17. --proof-metrics-file flag is parsed correctly ────────────────────────

def test_proof_metrics_file_flag_parsed():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        proof_path = _write_fake(tmp)
        rc, out_dir = _run_benchmark(
            ["--proof-metrics-file", str(proof_path)],
            tmp,
        )
        report = json.loads((out_dir / "benchmark_report.json").read_text(encoding="utf-8"))
        pm = report.get("imported_proof_metrics", {})
        assert pm.get("input_file") == str(proof_path)


# ── 18. official output clean — no imported_proof_metrics in results.json ─────

def test_official_output_clean_no_imported_proof_metrics():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        proof_path = _write_fake(tmp)
        rc, out_dir = _run_benchmark(
            ["--track1-official", "--no-receipts", "--proof-metrics-file", str(proof_path)],
            tmp,
        )
        results = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
        content = json.dumps(results)
        assert "imported_proof_metrics" not in content
        assert "scored_track1" not in content
        # Standard public fields must remain
        assert "format_version" in results
        assert "total_tasks" in results
        assert "tasks" in results
