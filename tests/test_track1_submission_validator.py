"""Tests for submission/track1/validate_output.py — strict Track 1 contract.

Pure stdlib + pytest tmp_path. No network, no Fireworks.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "validate_output", ROOT / "submission" / "track1" / "validate_output.py")
validator = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(validator)


TASKS = [
    {"task_id": "t1", "prompt": "What is 2+2?"},
    {"task_id": "t2", "prompt": "Name the capital of France."},
]
RESULTS = [
    {"task_id": "t1", "answer": "4"},
    {"task_id": "t2", "answer": "Paris"},
]


def _write(tmp_path: Path, name: str, data) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(data) if not isinstance(data, str) else data,
                 encoding="utf-8")
    return p


def _run(tmp_path: Path, tasks, results) -> int:
    t = _write(tmp_path, "tasks.json", tasks)
    r = _write(tmp_path, "results.json", results)
    return validator.validate(t, r)


def test_valid_output(tmp_path, capsys):
    assert _run(tmp_path, TASKS, RESULTS) == 0
    out = capsys.readouterr().out
    assert "TRACK1_OUTPUT_VALIDATION = PASS" in out
    assert "tasks_in = 2" in out
    assert "answers_out = 2" in out


def test_output_missing(tmp_path):
    t = _write(tmp_path, "tasks.json", TASKS)
    assert validator.validate(t, tmp_path / "nope.json") == 2


def test_output_invalid_json(tmp_path):
    t = _write(tmp_path, "tasks.json", TASKS)
    r = _write(tmp_path, "results.json", "{not json")
    assert validator.validate(t, r) == 2


def test_output_root_not_list(tmp_path):
    assert _run(tmp_path, TASKS, {"task_id": "t1", "answer": "4"}) == 3


def test_answer_field_missing(tmp_path):
    assert _run(tmp_path, TASKS, [{"task_id": "t1"},
                                  {"task_id": "t2", "answer": "Paris"}]) == 3


def test_extra_field(tmp_path):
    bad = [{"task_id": "t1", "answer": "4", "tokens": 12},
           {"task_id": "t2", "answer": "Paris"}]
    assert _run(tmp_path, TASKS, bad) == 3


def test_empty_answer(tmp_path):
    bad = [{"task_id": "t1", "answer": "   "},
           {"task_id": "t2", "answer": "Paris"}]
    assert _run(tmp_path, TASKS, bad) == 3


def test_null_answer(tmp_path):
    bad = [{"task_id": "t1", "answer": None},
           {"task_id": "t2", "answer": "Paris"}]
    assert _run(tmp_path, TASKS, bad) == 3


def test_duplicate_task_id_in_output(tmp_path):
    bad = [{"task_id": "t1", "answer": "4"},
           {"task_id": "t1", "answer": "again"}]
    assert _run(tmp_path, TASKS, bad) == 3


def test_missing_task_id(tmp_path):
    bad = [{"task_id": "t1", "answer": "4"},
           {"task_id": "t3", "answer": "?"}]
    assert _run(tmp_path, TASKS, bad) == 4


def test_unknown_task_id_only(tmp_path):
    one_task = [{"task_id": "t1", "prompt": "hi"}]
    assert _run(tmp_path, one_task, [{"task_id": "tX", "answer": "?"}]) == 4


def test_count_mismatch(tmp_path):
    assert _run(tmp_path, TASKS, [{"task_id": "t1", "answer": "4"}]) == 4


def test_input_invalid(tmp_path):
    t = _write(tmp_path, "tasks.json", "not json [")
    r = _write(tmp_path, "results.json", RESULTS)
    assert validator.validate(t, r) == 2


def test_input_extra_key(tmp_path):
    bad_tasks = [{"task_id": "t1", "prompt": "hi", "expected_route": "x"}]
    assert _run(tmp_path, bad_tasks, [{"task_id": "t1", "answer": "y"}]) == 3


def test_practice_file_is_valid_input():
    """The shipped practice set itself must satisfy the strict input contract."""
    tasks = json.loads((ROOT / "submission" / "track1" / "input" /
                        "practice_tasks.json").read_text(encoding="utf-8"))
    assert isinstance(tasks, list) and len(tasks) == 8
    ids = [t["task_id"] for t in tasks]
    assert len(set(ids)) == 8
    for t in tasks:
        assert set(t.keys()) == {"task_id", "prompt"}
        assert t["prompt"].strip()
