"""Track 1 output validator — strict schema check for /output/results.json.

Usage:
  python submission/track1/validate_output.py <tasks.json> <results.json>

Exit codes:
  0  output valid (strict schema, full input/output match)
  2  file missing or invalid JSON
  3  schema invalid (wrong root type, wrong keys, empty answers, duplicates)
  4  input/output mismatch (count, missing or unknown task_ids)

Stdlib only. No network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_FILE = 2
EXIT_SCHEMA = 3
EXIT_MISMATCH = 4


def _fail(code: int, message: str) -> int:
    print(f"TRACK1_OUTPUT_VALIDATION = FAIL ({message})", file=sys.stderr)
    return code


def _load_json_list(path: Path, label: str) -> tuple[list | None, int]:
    if not path.exists():
        return None, _fail(EXIT_FILE, f"{label} file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, _fail(EXIT_FILE, f"{label} is not valid JSON: {exc}")
    if not isinstance(data, list):
        return None, _fail(EXIT_SCHEMA, f"{label} root must be a JSON list, got {type(data).__name__}")
    return data, EXIT_OK


def validate(tasks_path: Path, results_path: Path) -> int:
    # ── Input contract ────────────────────────────────────────────────────
    tasks, code = _load_json_list(tasks_path, "input")
    if tasks is None:
        return code

    task_ids: list[str] = []
    for i, task in enumerate(tasks):
        if not isinstance(task, dict) or set(task.keys()) != {"task_id", "prompt"}:
            return _fail(EXIT_SCHEMA,
                         f"input task #{i} must have exactly keys task_id, prompt")
        tid = task["task_id"]
        if not isinstance(tid, str) or not tid.strip():
            return _fail(EXIT_SCHEMA, f"input task #{i} has empty/non-string task_id")
        task_ids.append(tid)
    if len(set(task_ids)) != len(task_ids):
        return _fail(EXIT_SCHEMA, "duplicate task_id in input")

    # ── Output contract ───────────────────────────────────────────────────
    results, code = _load_json_list(results_path, "output")
    if results is None:
        return code

    seen: list[str] = []
    empty_answers = 0
    for i, row in enumerate(results):
        if not isinstance(row, dict):
            return _fail(EXIT_SCHEMA, f"output row #{i} is not an object")
        if set(row.keys()) != {"task_id", "answer"}:
            extra = sorted(set(row.keys()) - {"task_id", "answer"})
            missing = sorted({"task_id", "answer"} - set(row.keys()))
            return _fail(EXIT_SCHEMA,
                         f"output row #{i} keys must be exactly task_id, answer "
                         f"(extra={extra}, missing={missing})")
        tid, answer = row["task_id"], row["answer"]
        if not isinstance(tid, str) or not tid.strip():
            return _fail(EXIT_SCHEMA, f"output row #{i} has empty/non-string task_id")
        if not isinstance(answer, str):
            return _fail(EXIT_SCHEMA, f"output row #{i} answer must be a string, got {type(answer).__name__}")
        if not answer.strip():
            empty_answers += 1
            return _fail(EXIT_SCHEMA, f"output row #{i} ({tid}) has an empty/whitespace answer")
        seen.append(tid)

    if len(set(seen)) != len(seen):
        dupes = sorted({t for t in seen if seen.count(t) > 1})
        return _fail(EXIT_SCHEMA, f"duplicate task_id in output: {dupes}")

    # ── Input/output match ────────────────────────────────────────────────
    if len(results) != len(tasks):
        return _fail(EXIT_MISMATCH,
                     f"answer count {len(results)} != task count {len(tasks)}")
    missing_ids = sorted(set(task_ids) - set(seen))
    unknown_ids = sorted(set(seen) - set(task_ids))
    if missing_ids:
        return _fail(EXIT_MISMATCH, f"missing task_ids in output: {missing_ids}")
    if unknown_ids:
        return _fail(EXIT_MISMATCH, f"unknown task_ids in output: {unknown_ids}")

    print("TRACK1_OUTPUT_VALIDATION = PASS")
    print(f"tasks_in = {len(tasks)}")
    print(f"answers_out = {len(results)}")
    print("schema = STRICT")
    print(f"missing = {len(missing_ids)}")
    print(f"extra = {len(unknown_ids)}")
    print(f"empty_answers = {empty_answers}")
    return EXIT_OK


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python validate_output.py <tasks.json> <results.json>",
              file=sys.stderr)
        return EXIT_FILE
    return validate(Path(argv[0]), Path(argv[1]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
