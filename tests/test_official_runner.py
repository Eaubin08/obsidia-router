"""Tests — official runner I/O : --tasks-file, --out-dir, --no-receipts, Dockerfile."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent

_MINIMAL_TASKS = [
    {"id": "test_local_status", "request": "statut du systeme", "expected_route": "no_model_needed"},
    {"id": "test_local_hold", "request": "execute this script", "expected_route": "hold_commands_only"},
]

_FIREWORKS_TASK = {
    "id": "test_fw_task",
    "request": "compare cache-aside and write-through strategies",
    "expected_route": "fireworks",
}

_MOCK_FW_RESULT = {
    "text": "Cache-aside: lazy loading. Write-through: synchronous write.",
    "model": "accounts/fireworks/models/gpt-oss-120b",
    "total_tokens": 80,
    "prompt_tokens": 20,
    "completion_tokens": 60,
    "latency_s": 0.5,
    "dry_run": False,
    "fireworks_tokens": 80,
}


def _write_tasks(tmp: Path, tasks: list[dict]) -> Path:
    p = tmp / "tasks.json"
    p.write_text(json.dumps(tasks), encoding="utf-8")
    return p


# ── 1. --tasks-file utilisé réellement ───────────────────────────────────────

def test_run_benchmark_uses_tasks_file():
    """--tasks-file pointe sur des tâches custom → ce sont celles-ci qui sont traitées."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        tasks_path = _write_tasks(tmp, _MINIMAL_TASKS)
        out_dir = tmp / "out"

        orig_argv = sys.argv
        try:
            sys.argv = [
                "run_benchmark.py",
                "--tasks-file", str(tasks_path),
                "--out-dir", str(out_dir),
                "--no-receipts",
            ]
            from benchmarks.run_benchmark import main
            rc = main()
        finally:
            sys.argv = orig_argv

        # Le runner doit avoir écrit benchmark_report.json dans out_dir
        report_path = out_dir / "benchmark_report.json"
        assert report_path.exists(), "benchmark_report.json absent"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        # Uniquement 2 tâches, pas les 18 de benchmarks/tasks.json
        total = report.get("obsidia", {}).get("total_tasks", report.get("route_accuracy", -1))
        tasks_in_report = report.get("tasks", [])
        assert len(tasks_in_report) == len(_MINIMAL_TASKS), (
            f"Attendu {len(_MINIMAL_TASKS)} tâches, obtenu {len(tasks_in_report)}"
        )
        ids = {t["id"] for t in tasks_in_report}
        assert "test_local_status" in ids
        assert "test_local_hold" in ids
        # Ne contient pas les tâches de benchmarks/tasks.json
        assert "status_simple" not in ids


# ── 2. --tasks-file manquant → erreur claire, pas de fallback silencieux ─────

def test_run_benchmark_missing_explicit_tasks_file_fails():
    """--tasks-file vers un fichier inexistant → return code 2, pas de fallback."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        absent = tmp / "does_not_exist.json"
        out_dir = tmp / "out"

        orig_argv = sys.argv
        try:
            sys.argv = [
                "run_benchmark.py",
                "--tasks-file", str(absent),
                "--out-dir", str(out_dir),
                "--no-receipts",
            ]
            from benchmarks.run_benchmark import main
            rc = main()
        finally:
            sys.argv = orig_argv

        assert rc == 2, f"Attendu rc=2 (fichier absent), obtenu rc={rc}"
        # Aucun résultat ne doit avoir été écrit
        assert not (out_dir / "results.json").exists()


# ── 3. --out-dir écrit results.json dans le bon dossier ──────────────────────

def test_run_benchmark_out_dir_writes_results_json():
    """--out-dir custom → results.json présent dans ce dossier."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        tasks_path = _write_tasks(tmp, _MINIMAL_TASKS)
        out_dir = tmp / "custom_output"

        orig_argv = sys.argv
        try:
            sys.argv = [
                "run_benchmark.py",
                "--track1-official",
                "--tasks-file", str(tasks_path),
                "--out-dir", str(out_dir),
                "--no-receipts",
            ]
            from benchmarks.run_benchmark import main
            rc = main()
        finally:
            sys.argv = orig_argv

        # results.json doit être dans out_dir (pas dans ROOT/results)
        assert (out_dir / "results.json").exists(), "results.json absent du out_dir"
        assert (out_dir / "benchmark_report.json").exists(), "benchmark_report.json absent"


# ── 4. results.json public clean (pas de champs internes) ────────────────────

def test_official_results_json_clean():
    """results.json public ne doit pas contenir de champs internes."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        tasks_path = _write_tasks(tmp, _MINIMAL_TASKS)
        out_dir = tmp / "out"

        orig_argv = sys.argv
        try:
            sys.argv = [
                "run_benchmark.py",
                "--track1-official",
                "--tasks-file", str(tasks_path),
                "--out-dir", str(out_dir),
                "--no-receipts",
            ]
            from benchmarks.run_benchmark import main
            rc = main()
        finally:
            sys.argv = orig_argv

        results_path = out_dir / "results.json"
        assert results_path.exists()
        content = results_path.read_text(encoding="utf-8")
        results = json.loads(content)

        # Clés publiques obligatoires
        for key in ("format_version", "total_tasks", "tasks", "route_accuracy"):
            assert key in results, f"Clé publique manquante: {key}"

        # Champs internes interdits : vérification par clé JSON exacte
        for forbidden_key in ("remote_answer_contract", "metrics_coverage",
                              "receipts", "private_policy"):
            assert f'"{forbidden_key}"' not in content, (
                f"Clé interne '\"{forbidden_key}\"' trouvée dans results.json"
            )
        # "ir" est une clé interne courte — vérifier le pattern clé JSON
        assert '"ir":' not in content, "Clé interne '\"ir\":' trouvée dans results.json"

        # Chaque tâche doit avoir les champs attendus
        for t in results["tasks"]:
            assert "id" in t
            assert "route" in t
            assert "answer" in t
            assert "tokens_used" in t


# ── 5. Dockerfile contient les arguments officiels ────────────────────────────

def test_dockerfile_uses_input_output():
    """Dockerfile doit référencer /input/tasks.json, /output, --track1-official, --no-receipts."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "/input/tasks.json" in dockerfile, "Dockerfile sans /input/tasks.json"
    assert "/output" in dockerfile, "Dockerfile sans /output"
    assert "--track1-official" in dockerfile, "Dockerfile sans --track1-official"
    assert "--no-receipts" in dockerfile, "Dockerfile sans --no-receipts"


# ── 6. Mode local par défaut fonctionne encore ───────────────────────────────

def test_default_local_mode_still_uses_benchmarks_tasks():
    """Sans --tasks-file, le mode local lit benchmarks/tasks.json (18 tâches)."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        out_dir = tmp / "out"

        orig_argv = sys.argv
        try:
            sys.argv = [
                "run_benchmark.py",
                "--out-dir", str(out_dir),
            ]
            from benchmarks.run_benchmark import main
            rc = main()
        finally:
            sys.argv = orig_argv

        report_path = out_dir / "benchmark_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        tasks_in_report = report.get("tasks", [])
        # benchmarks/tasks.json a 18 tâches
        assert len(tasks_in_report) == 18, (
            f"Mode local doit traiter 18 tâches, obtenu {len(tasks_in_report)}"
        )


# ── 7. --no-receipts supprime receipts_internal.json ─────────────────────────

def test_no_receipts_skips_receipts_internal():
    """--no-receipts → receipts_internal.json absent de out_dir."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        tasks_path = _write_tasks(tmp, _MINIMAL_TASKS)
        out_dir = tmp / "out"

        orig_argv = sys.argv
        try:
            sys.argv = [
                "run_benchmark.py",
                "--track1-official",
                "--tasks-file", str(tasks_path),
                "--out-dir", str(out_dir),
                "--no-receipts",
            ]
            from benchmarks.run_benchmark import main
            rc = main()
        finally:
            sys.argv = orig_argv

        assert not (out_dir / "receipts_internal.json").exists(), (
            "receipts_internal.json présent malgré --no-receipts"
        )
        assert (out_dir / "results.json").exists()


# ── 8. Sans --no-receipts, receipts_internal.json est présent (mode local) ───

def test_without_no_receipts_writes_receipts():
    """Sans --no-receipts → receipts_internal.json est écrit (mode audit local)."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        tasks_path = _write_tasks(tmp, _MINIMAL_TASKS)
        out_dir = tmp / "out"

        orig_argv = sys.argv
        try:
            sys.argv = [
                "run_benchmark.py",
                "--track1-official",
                "--tasks-file", str(tasks_path),
                "--out-dir", str(out_dir),
            ]
            from benchmarks.run_benchmark import main
            rc = main()
        finally:
            sys.argv = orig_argv

        assert (out_dir / "receipts_internal.json").exists(), (
            "receipts_internal.json absent en mode local (sans --no-receipts)"
        )
