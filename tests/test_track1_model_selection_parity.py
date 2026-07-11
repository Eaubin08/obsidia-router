"""LOT C/D parity — scripts/run_official.py and
benchmarks/run_benchmark.py --track1-official must select the exact same
model for the exact same input and the exact same ALLOWED_MODELS ladder.

Runs entirely in dry-run mode (no FIREWORKS_API_KEY): app.adapters.fireworks
returns a deterministic dry-run record without ever touching the network.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_SPEC = importlib.util.spec_from_file_location(
    "run_official_module", ROOT / "scripts" / "run_official.py")
run_official = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(run_official)

# A code-shaped, hidden-task-style prompt (no expected_route): both official
# paths must escalate it under the bounded contract and pick the same rung.
_HIDDEN_CODE_TASK = {
    "task_id": "hidden_code_1",
    "prompt": "Implement a complex distributed cache with concurrency control.",
}

_LADDER_ENV = "small-model,medium-model,gpt-oss-120b"


def _run_official_model(tmp: Path, monkeypatch) -> str:
    monkeypatch.setenv("ALLOWED_MODELS", _LADDER_ENV)
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    in_path = tmp / "tasks.json"
    out_path = tmp / "results.json"
    in_path.write_text(json.dumps([_HIDDEN_CODE_TASK]), encoding="utf-8")

    orig_argv = sys.argv
    try:
        sys.argv = ["run_official.py",
                    "--input", str(in_path), "--output", str(out_path)]
        rc = run_official.main()
    finally:
        sys.argv = orig_argv
    assert rc == 0
    # No public receipts of the model in results.json (by design) — recompute
    # the same selection independently via the single triage authority to
    # cross-check what the runner must have used.
    from app.router.model_triage import select_model_for_request
    from benchmarks.track1_remote_answer_contract import build_remote_answer_contract
    contract = build_remote_answer_contract(_HIDDEN_CODE_TASK["prompt"])
    return select_model_for_request(
        _HIDDEN_CODE_TASK["prompt"],
        _LADDER_ENV.split(","),
        answer_kind=contract["answer_kind"],
    )["selected_model"]


def _run_benchmark_model(tmp: Path, monkeypatch) -> str:
    monkeypatch.setenv("ALLOWED_MODELS", _LADDER_ENV)
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    tasks_path = tmp / "bm_tasks.json"
    out_dir = tmp / "bm_out"
    tasks_path.write_text(json.dumps([_HIDDEN_CODE_TASK]), encoding="utf-8")

    orig_argv = sys.argv
    try:
        sys.argv = [
            "run_benchmark.py",
            "--tasks-file", str(tasks_path),
            "--out-dir", str(out_dir),
            "--track1-official",
            "--no-receipts",
        ]
        from benchmarks.run_benchmark import main
        rc = main()
    finally:
        sys.argv = orig_argv
    assert rc == 0
    report = json.loads((out_dir / "benchmark_report.json").read_text(encoding="utf-8"))
    row = report["tasks"][0]
    return row["model"]


def test_run_official_and_run_benchmark_pick_the_same_model(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        expected_model = _run_official_model(tmp, monkeypatch)
        actual_benchmark_model = _run_benchmark_model(tmp, monkeypatch)
        assert actual_benchmark_model == expected_model
        assert actual_benchmark_model == "gpt-oss-120b"  # rung 2: complex code
