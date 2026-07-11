"""PRACTICE_DETERMINISTIC_GRADER — shared grading authority (LOT H).

Deterministic regex graders for the 8 official practice tasks of
submission/track1/input/practice_tasks.json. Extracted from the LOT G4
model selection benchmark so that answer_accuracy.py, the model matrix and
any rehearsal all grade with the exact same rules.

Never presented as the hidden AMD judge score.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRACTICE_TASKS_PATH = ROOT / "submission" / "track1" / "input" / "practice_tasks.json"

GRADER_LABEL = "PRACTICE_DETERMINISTIC_GRADER"

# (task_id, category, [required regex — ALL must match, re.I | re.M])
PRACTICE_GRADERS: list[tuple[str, str, list[str]]] = [
    ("practice-01", "factual",
     [r"canberra"]),
    ("practice-02", "math_reasoning",
     [r"\b72\b"]),                       # 180 km / 2.5 h = 72 km/h
    ("practice-03", "sentiment",
     [r"neutral|mixed"]),                # mixed review, forced 3-way choice
    ("practice-04", "summarisation",
     [r"solar", r"[.!?]"]),
    ("practice-05", "ner",
     [r"satya\s+nadella", r"microsoft", r"nairobi", r"cambridge"]),
    ("practice-06", "code_debugging",
     [r"return\s+total\s*/\s*len\(numbers\)(?!\s*\+)"]),  # fix removes "+ 1"
    ("practice-07", "logical_reasoning",
     [r"\byes\b"]),
    ("practice-08", "code_generation",
     [r"def\s+\w+", r"%\s*2\s*==\s*0|even"]),
]

GRADERS_BY_ID = {tid: (cat, checks) for tid, cat, checks in PRACTICE_GRADERS}


def load_practice_tasks() -> list[dict]:
    """Stable mapping task_id / category / prompt from practice_tasks.json."""
    raw = json.loads(PRACTICE_TASKS_PATH.read_text(encoding="utf-8"))
    tasks = []
    for t in raw:
        tid = t["task_id"]
        cat, _ = GRADERS_BY_ID[tid]
        tasks.append({"task_id": tid, "category": cat, "prompt": t["prompt"]})
    return tasks


def grade_answer(task_id: str, answer: str) -> dict:
    """Regex ALL-match; dry-run and [error] outputs always fail."""
    cat, checks = GRADERS_BY_ID[task_id]
    text = answer or ""
    if "[dry-run]" in text or "[error]" in text:
        return {"task_id": task_id, "category": cat, "grade": "FAIL",
                "pass": False, "failure_reason": "dry_run_or_error_output",
                "format_compliant": False}
    missing = [rx for rx in checks if not re.search(rx, text, re.I | re.M)]
    ok = not missing
    return {
        "task_id": task_id,
        "category": cat,
        "grade": "PASS" if ok else "FAIL",
        "pass": ok,
        "failure_reason": None if ok else f"missing_patterns:{len(missing)}",
        "format_compliant": bool(text.strip()),
    }


def _extract_code_block(text: str) -> str:
    """Safety net: if a model prefixed code with reasoning, extract the code.

    Priority: ```python fence -> bare fence -> first `def ` occurrence.
    Falls back to the original text.
    """
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.S)
    if m:
        return m.group(1).strip()
    m = re.search(r"(def\s+\w+.*)", text, re.S)
    if m:
        return m.group(1).strip()
    return text
