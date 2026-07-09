"""AMD Track 1 harness compatibility — official input/output schema.

The harness contract:
  input  /input/tasks.json  : [{"task_id": ..., "prompt": ...}, ...]
  output /output/results.json: [{"task_id": ..., "answer": ...}, ...]
  answers in English, nothing else in the official file.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OFFICIAL_TASKS = [
    {"task_id": "practice-01", "prompt": "What is the capital of Australia?"},
    {"task_id": "practice-02", "prompt": "status"},
    {"task_id": "practice-03", "prompt": "push this to production now"},
    {"task_id": "practice-04", "prompt": "Summarize: the quick brown fox jumps over the lazy dog."},
]


def _run_official(tmp_path: Path) -> list:
    tasks_file = tmp_path / "tasks.json"
    out_dir = tmp_path / "out"
    tasks_file.write_text(json.dumps(OFFICIAL_TASKS), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "benchmarks/run_benchmark.py", "--track1-official",
         "--tasks-file", str(tasks_file), "--out-dir", str(out_dir),
         "--no-receipts"],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-800:]
    return json.loads((out_dir / "results.json").read_text(encoding="utf-8"))


def test_official_input_keys_accepted(tmp_path):
    """task_id/prompt (schema AMD) doit etre accepte tel quel."""
    results = _run_official(tmp_path)
    assert isinstance(results, list)
    assert len(results) == len(OFFICIAL_TASKS)


def test_official_output_is_pure_list(tmp_path):
    """results.json officiel = liste [{task_id, answer}] et RIEN d'autre."""
    results = _run_official(tmp_path)
    assert isinstance(results, list), "official output must be a JSON list"
    ids = set()
    for row in results:
        assert set(row.keys()) == {"task_id", "answer"}, row.keys()
        assert isinstance(row["task_id"], str) and row["task_id"]
        assert isinstance(row["answer"], str) and row["answer"].strip()
        ids.add(row["task_id"])
    assert ids == {t["task_id"] for t in OFFICIAL_TASKS}
    leaked = json.dumps(results)
    for forbidden in ("format_version", "total_tasks", "route_accuracy",
                      "tokens_used", "route_correct", "KX108", "gate_verdict"):
        assert forbidden not in leaked, f"internal field leaked: {forbidden}"


def test_no_receipts_in_official_outdir(tmp_path):
    _run_official(tmp_path)
    assert not (tmp_path / "out" / "receipts_internal.json").exists()


def test_internal_schema_still_works(tmp_path):
    """Le mode local (sans --no-receipts) garde le format riche interne."""
    from benchmarks.track1_runner import build_results, normalize_task
    rows = [{"id": "t1", "actual_route": "no_model_needed",
             "intent_type": "status", "fireworks_tokens": 0}]
    rich = build_results(rows)
    assert rich["format_version"] == "track1_v1"
    assert rich["tasks"][0]["id"] == "t1"
    n = normalize_task({"task_id": "x", "prompt": "y"})
    assert n["id"] == "x" and n["request"] == "y"
