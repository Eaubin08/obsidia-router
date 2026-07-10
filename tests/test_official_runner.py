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
        # Mode officiel AMD : results.json est une LISTE pure {task_id, answer}.
        assert isinstance(results, list)
        for row in results:
            assert set(row.keys()) == {"task_id", "answer"}
        for key in ():
            assert key in results, f"Clé publique manquante: {key}"

        # Champs internes interdits : vérification par clé JSON exacte
        for forbidden_key in ("remote_answer_contract", "metrics_coverage",
                              "receipts", "private_policy"):
            assert f'"{forbidden_key}"' not in content, (
                f"Clé interne '\"{forbidden_key}\"' trouvée dans results.json"
            )
        # "ir" est une clé interne courte — vérifier le pattern clé JSON
        assert '"ir":' not in content, "Clé interne '\"ir\":' trouvée dans results.json"

        # Schema officiel AMD : chaque ligne = {task_id, answer} uniquement
        for t in results:
            assert set(t.keys()) == {"task_id", "answer"}


# ── 5. Dockerfile contient les arguments officiels ────────────────────────────

def test_dockerfile_uses_input_output():
    """Dockerfile doit referencer le runner slim et les chemins /input et /output."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    # Le runner slim lit /input et ecrit dans /output par defaut.
    assert "/input" in dockerfile, "Dockerfile sans /input"
    assert "/output" in dockerfile, "Dockerfile sans /output"
    # Le runner officiel slim doit etre reference dans le CMD.
    assert "run_official" in dockerfile or "--track1-official" in dockerfile, (
        "Dockerfile sans runner officiel (run_official ou --track1-official)"
    )


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


# ── 9. Escalation guard — should_escalate_clarification_to_fireworks ─────────

from benchmarks.track1_escalation_guard import (  # noqa: E402
    should_escalate_clarification_to_fireworks as _guard,
)


def _make_clarify_decision(
    intent_type: str = "unknown",
    open_world: bool = False,
    gate_verdict: str = "CLARIFY",
) -> dict:
    return {
        "route": "clarification_needed",
        "ir": {"intent_type": intent_type, "open_world": open_world},
        "gate": {"verdict": gate_verdict},
    }


_HIDDEN_TASK: dict = {}  # no expected_route — simulates AMD hidden task


@pytest.mark.parametrize("prompt", [
    # tokens actionnels courts
    "ok",
    "ok vas-y",
    "ok vas-y fais le",
    "fais-le",
    "continue",
    "go",
    "lance",
    "applique",
    "fais le truc dont on parlait",
    "vas-y",
    "reprends",
    "proceed",
    # demonstratifs vagues — verbe present mais objet non exploitable
    "analyse ça",
    "compare ça",
    "regarde ça",
    "fais ça",
    "explain this",
    "compare that",
    "describe it",
])
def test_escalation_guard_rejects_short_and_vague(prompt):
    """Prompts courts / actionnels / demonstratifs vagues -> False (0 token)."""
    decision = _make_clarify_decision()
    assert _guard(_HIDDEN_TASK, prompt, decision) is False, (
        f"Expected False: {prompt!r}"
    )


def test_escalation_guard_open_world_does_not_bypass_ok():
    """'ok' + open_world=True -> False : bloque step 5a avant step 6."""
    decision = _make_clarify_decision(open_world=True)
    assert _guard(_HIDDEN_TASK, "ok", decision) is False


def test_escalation_guard_open_world_does_not_bypass_actional_multi():
    """'ok vas-y fais le' + open_world=True -> False : bloque step 5a."""
    decision = _make_clarify_decision(open_world=True)
    assert _guard(_HIDDEN_TASK, "ok vas-y fais le", decision) is False


def test_escalation_guard_open_world_does_not_bypass_vague_demo():
    """'analyse ca' + open_world=True -> False : bloque step 5b."""
    decision = _make_clarify_decision(open_world=True)
    assert _guard(_HIDDEN_TASK, "analyse ça", decision) is False


def test_escalation_guard_open_world_with_informational():
    """Vraie question ouverte + open_world=True -> True : step 6."""
    decision = _make_clarify_decision(open_world=True)
    assert _guard(
        _HIDDEN_TASK,
        "Explain the implications of distributed cache consistency.",
        decision,
    ) is True


@pytest.mark.parametrize("prompt", [
    "Compare microservices and monolithic architectures for a payment system.",
    "Write a Python function that implements a thread-safe LRU cache.",
    "Explain the difference between TCP and UDP.",
    "How should I design a rate limiter for an API?",
    "What is the CAP theorem?",
    "Analyse the trade-offs between SQL and NoSQL databases.",
    "Give me an example of the observer design pattern in Python.",
])
def test_escalation_guard_allows_informational(prompt):
    """Vraies questions informationnelles -> True : step 7."""
    decision = _make_clarify_decision()
    assert _guard(_HIDDEN_TASK, prompt, decision) is True, (
        f"Expected True: {prompt!r}"
    )


def test_escalation_guard_respects_expected_route():
    """expected_route present -> False : step 2."""
    validation = {"expected_route": "clarification_needed"}
    assert _guard(validation, "Compare X and Y in detail.", _make_clarify_decision()) is False


def test_escalation_guard_respects_hold_gate():
    """Gate HOLD -> False : step 3."""
    assert _guard(_HIDDEN_TASK, "Compare microservices and monolithic.",
                  _make_clarify_decision(gate_verdict="HOLD")) is False


def test_escalation_guard_respects_deny_gate():
    """Gate DENY -> False : step 3."""
    assert _guard(_HIDDEN_TASK, "Explain the CAP theorem.",
                  _make_clarify_decision(gate_verdict="DENY")) is False


def test_escalation_guard_respects_block_gate():
    """Gate BLOCK -> False : step 3."""
    assert _guard(_HIDDEN_TASK, "Write a sorting function.",
                  _make_clarify_decision(gate_verdict="BLOCK")) is False


def test_escalation_guard_respects_world_action_intent():
    """Intent world_action -> False : step 4."""
    assert _guard(_HIDDEN_TASK, "push all current changes to production",
                  _make_clarify_decision(intent_type="world_action")) is False


def test_escalation_guard_non_clarify_route():
    """Route != clarification_needed -> False : step 1."""
    decision = {"route": "fireworks", "ir": {}, "gate": {"verdict": "ALLOW"}}
    assert _guard(_HIDDEN_TASK, "Compare X and Y in detail.", decision) is False
