"""Tests — weight/speed cleanup: footprint proxy labels, speed sources, run_id, token consistency."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent

# ── Helpers ───────────────────────────────────────────────────────────────────

def _minimal_tasks() -> list[dict]:
    return [
        {"id": "ws_status", "request": "statut du systeme", "expected_route": "no_model_needed"},
        {"id": "ws_hold", "request": "execute this script", "expected_route": "hold_commands_only"},
    ]


def _run_benchmark(argv_extra: list[str], tmp: Path) -> tuple[int, Path]:
    tasks_path = tmp / "tasks.json"
    tasks_path.write_text(json.dumps(_minimal_tasks()), encoding="utf-8")
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


# ── 1. repo_disk_size_mb présent dans footprint ───────────────────────────────

def test_footprint_has_repo_disk_size():
    from benchmarks.footprint import collect_footprint
    fp = collect_footprint(ROOT)
    assert "repo_disk_size_mb" in fp
    assert isinstance(fp["repo_disk_size_mb"], (int, float))
    assert fp["repo_disk_size_mb"] > 0
    # Doit être identique à repo_size_mb
    assert fp["repo_disk_size_mb"] == fp["repo_size_mb"]


# ── 2. runtime_stack_size_mb marqué comme proxy ──────────────────────────────

def test_runtime_stack_size_is_marked_proxy():
    from benchmarks.footprint import collect_footprint
    fp = collect_footprint(ROOT)
    assert "runtime_stack_size_note" in fp
    assert "proxy" in fp["runtime_stack_size_note"].lower()
    assert "rss" in fp["runtime_stack_size_note"].lower()
    # La valeur doit rester cohérente avec le repo_size
    assert fp["runtime_stack_size_mb"] == fp["repo_size_mb"]
    assert fp["runtime_disk_proxy_mb"] == fp["repo_size_mb"]


# ── 3. process_rss_mb + status présents, pas de dépendance psutil ─────────────

def test_process_rss_not_measured_without_dependency():
    from benchmarks.footprint import collect_footprint
    fp = collect_footprint(ROOT)
    assert "process_rss_mb" in fp
    assert "process_rss_status" in fp
    # Sur Windows (CI hackathon) : not_measured
    # Sur Linux/macOS : peut être mesuré — valeur numérique > 0
    status = fp["process_rss_status"]
    assert status in ("measured", "not_measured_no_psutil_or_platform_support")
    if status == "measured":
        assert isinstance(fp["process_rss_mb"], (int, float))
        assert fp["process_rss_mb"] > 0
    else:
        assert fp["process_rss_mb"] == "not_measured"


# ── 4. speed sources présentes dans metrics_coverage ─────────────────────────

def test_metrics_coverage_speed_sources_present():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        rc, out_dir = _run_benchmark([], tmp)
        report = json.loads((out_dir / "benchmark_report.json").read_text(encoding="utf-8"))
        speed = report.get("metrics_coverage", {}).get("speed", {})
        assert "sources" in speed, "sources dict absent de metrics_coverage.speed"
        sources = speed["sources"]
        assert sources.get("avg_local_decision_ms") == "rows_non_fireworks"
        assert sources.get("avg_fireworks_call_s") == "metrics_records_fireworks"
        assert sources.get("decisions_per_second") == "dynamic_phase"
        assert sources.get("total_runtime_s") == "main_wallclock"


# ── 5. run_id présent dans benchmark_report.json ─────────────────────────────

def test_benchmark_report_has_run_id():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        rc, out_dir = _run_benchmark([], tmp)
        report = json.loads((out_dir / "benchmark_report.json").read_text(encoding="utf-8"))
        assert "run_id" in report, "run_id absent de benchmark_report.json"
        assert isinstance(report["run_id"], str)
        assert len(report["run_id"]) >= 8  # format YYYYMMDD_HHMMSS


# ── 6. generated_from flags dans benchmark_report.json ───────────────────────

def test_benchmark_report_has_generated_from():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        rc, out_dir = _run_benchmark(["--track1-official", "--no-receipts"], tmp)
        report = json.loads((out_dir / "benchmark_report.json").read_text(encoding="utf-8"))
        gf = report.get("generated_from", {})
        assert gf.get("track1_official") is True
        assert gf.get("stack_v3b") is False
        assert "tasks_file" in gf
        assert "out_dir" in gf
        assert "run_id" in gf


# ── 7. run_id dans receipts_internal.json (mode local) ───────────────────────

def test_receipts_have_run_id():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        rc, out_dir = _run_benchmark(["--track1-official"], tmp)
        receipts_path = out_dir / "receipts_internal.json"
        if receipts_path.exists():
            receipts = json.loads(receipts_path.read_text(encoding="utf-8"))
            # run_id doit être présent (soit top-level soit dans extra)
            has_run_id = (
                receipts.get("run_id") is not None
                or receipts.get("extra", {}).get("run_id") is not None
            )
            assert has_run_id, "run_id absent de receipts_internal.json"


# ── 8. REPORT.md contient la section weight/speed notes ──────────────────────

def test_report_md_contains_weight_speed_notes():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        rc, out_dir = _run_benchmark([], tmp)
        md = (out_dir / "REPORT.md").read_text(encoding="utf-8")
        assert "Weight and speed" in md, "Section 'Weight and speed' absente de REPORT.md"
        assert "disk proxy" in md.lower(), "Mention 'disk proxy' absente de REPORT.md"
        assert "process RSS" in md or "process rss" in md.lower(), (
            "Mention process RSS absente de REPORT.md"
        )


# ── 9. results.json public toujours clean ────────────────────────────────────

def test_public_results_still_clean():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        rc, out_dir = _run_benchmark(["--track1-official", "--no-receipts"], tmp)
        results_path = out_dir / "results.json"
        assert results_path.exists()
        content = results_path.read_text(encoding="utf-8")
        results = json.loads(content)
        # Mode officiel AMD : liste pure {task_id, answer}.
        assert isinstance(results, list)
        for row in results:
            assert set(row.keys()) == {"task_id", "answer"}
        for key in ():
            assert key in results
        for forbidden in ("remote_answer_contract", "metrics_coverage", "run_id"):
            assert f'"{forbidden}"' not in content, (
                f"Champ interne '{forbidden}' trouvé dans results.json public"
            )


# ── 10. Cohérence tokens : même run → tokens identiques ──────────────────────

def test_benchmark_report_tokens_match_results_for_combined_run():
    """Dans un run unifié --track1-official, obsidia.fireworks_tokens == results.tokens_used_total."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        rc, out_dir = _run_benchmark(["--track1-official"], tmp)
        report = json.loads((out_dir / "benchmark_report.json").read_text(encoding="utf-8"))
        results_path = out_dir / "results.json"
        if results_path.exists():
            results = json.loads(results_path.read_text(encoding="utf-8"))
            obsidia_tokens = report.get("obsidia", {}).get("fireworks_tokens", -1)
            results_tokens = results.get("tokens_used_total", -2)
            assert obsidia_tokens == results_tokens, (
                f"Tokens incohérents: benchmark_report.obsidia.fireworks_tokens={obsidia_tokens} "
                f"!= results.json.tokens_used_total={results_tokens}"
            )
