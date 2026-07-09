"""Mini count-driven check: N tasks in -> N results out, no hardcoded 18.

Proves that the official runner is purely input-count-driven.
Does not validate answer quality — only shape and schema.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent

_MOCK = {
    "text": "ok", "model": "x",
    "total_tokens": 1, "prompt_tokens": 1,
    "completion_tokens": 0, "latency_s": 0.0, "dry_run": False,
}


def _run_n(n: int, tmp: Path) -> list[dict]:
    tasks = [{"task_id": f"t{i}", "prompt": "status"} for i in range(n)]
    tf = tmp / "tasks.json"
    od = tmp / "out"
    tf.write_text(json.dumps(tasks), encoding="utf-8")
    orig = sys.argv
    try:
        sys.argv = [
            "run_benchmark.py", "--track1-official",
            "--tasks-file", str(tf), "--out-dir", str(od), "--no-receipts",
        ]
        with patch("app.adapters.fireworks.chat", return_value=_MOCK):
            from benchmarks.run_benchmark import main
            main()
    finally:
        sys.argv = orig
    return json.loads((od / "results.json").read_text(encoding="utf-8"))


def test_1_task_in_1_out(tmp_path):
    assert len(_run_n(1, tmp_path)) == 1


def test_5_tasks_in_5_out(tmp_path):
    assert len(_run_n(5, tmp_path)) == 5


def test_19_tasks_in_19_out(tmp_path):
    results = _run_n(19, tmp_path)
    assert len(results) == 19
    ids_out = {r["task_id"] for r in results}
    ids_in = {f"t{i}" for i in range(19)}
    assert ids_out == ids_in


def test_output_schema_strict(tmp_path):
    results = _run_n(5, tmp_path)
    for row in results:
        assert set(row.keys()) == {"task_id", "answer"}
        assert isinstance(row["answer"], str) and row["answer"].strip()
