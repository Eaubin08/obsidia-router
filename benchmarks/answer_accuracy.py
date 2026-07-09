"""Answer accuracy by category — local grading on the 8 official practice tasks.

Route accuracy measures WHERE a request goes; this measures whether the final
ANSWER is right, per AMD category. Grading is keyword-based against the known
practice answers (the hidden set stays LLM-judged by the harness — this is the
local proxy the guide recommends running before spending a submission slot).

Usage (live, spends a few hundred Fireworks tokens):
    python benchmarks/answer_accuracy.py
Writes results/answer_accuracy_by_category.json and prints a summary table.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (task_id, category, prompt, [required regex — ALL must match the answer])
PRACTICE = [
    ("practice-01", "factual",
     "What is the capital of Australia, and what body of water is it near?",
     [r"canberra", r"burley\s*griffin"]),
    ("practice-02", "math_reasoning",
     "A store has 240 items. It sells 15% on Monday and 60 more on Tuesday. "
     "How many items remain?",
     [r"\b144\b"]),
    ("practice-03", "sentiment",
     "Classify the sentiment of this review: The battery life is great, but "
     "the screen scratches too easily.",
     [r"mixed|both positive and negative|neutral"]),
    ("practice-04", "summarisation",
     "Summarize the following in exactly one sentence: The Obsidia router "
     "compiles every request into a structured intent, checks deterministic "
     "gates, and only escalates to a remote model when local structure "
     "cannot answer, which reduces token spend substantially.",
     [r"[.!?]"]),
    ("practice-05", "ner",
     "Extract all named entities and their types from: Maria Sanchez joined "
     "Fireworks AI in Berlin last March.",
     [r"maria sanchez", r"fireworks ai", r"berlin", r"march"]),
    ("practice-06", "code_debugging",
     "This function should return the max of a list but has a bug: "
     "def get_max(nums): return nums[0]. Find and fix it.",
     [r"max\(|for\s+\w+\s+in"]),
    ("practice-07", "logical_reasoning",
     "Three friends, Sam, Jo, and Lee, each own a different pet: cat, dog, "
     "bird. Sam does not own the bird. Jo owns the dog. Who owns the cat?",
     [r"\bsam\b"]),
    ("practice-08", "code_generation",
     "Write a Python function that returns the second-largest number in a "
     "list, handling duplicates correctly.",
     [r"def\s+\w+", r"sorted|sort|max"]),
]


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tasks_file = Path(td) / "tasks.json"
        out_dir = Path(td) / "out"
        tasks_file.write_text(json.dumps(
            [{"task_id": t, "prompt": p} for t, _, p, _ in PRACTICE]),
            encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "benchmarks/run_benchmark.py", "--track1-official",
             "--tasks-file", str(tasks_file), "--out-dir", str(out_dir),
             "--no-receipts"],
            cwd=ROOT, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            print(proc.stderr[-500:])
            return 1
        answers = {r["task_id"]: r["answer"] for r in
                   json.loads((out_dir / "results.json").read_text(encoding="utf-8"))}

    by_cat: dict = {}
    print(f"{'category':<20} {'task':<13} {'grade':<5} answer")
    for task_id, cat, _, checks in PRACTICE:
        ans = answers.get(task_id, "")
        ok = all(re.search(rx, ans, re.I | re.M) for rx in checks) \
            and "[dry-run]" not in ans and "[error]" not in ans
        by_cat.setdefault(cat, []).append(ok)
        print(f"{cat:<20} {task_id:<13} {'PASS' if ok else 'FAIL':<5} {ans[:60]!r}")

    summary = {cat: {"passed": sum(v), "total": len(v)} for cat, v in by_cat.items()}
    total_ok = sum(s["passed"] for s in summary.values())
    payload = {"answer_accuracy_by_category": summary,
               "overall": {"passed": total_ok, "total": len(PRACTICE),
                           "rate": round(total_ok / len(PRACTICE), 4)},
               "grading": "keyword_proxy_local (hidden set is LLM-judged)"}
    out = ROOT / "results" / "answer_accuracy_by_category.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\noverall: {total_ok}/{len(PRACTICE)}  -> {out}")
    return 0 if total_ok == len(PRACTICE) else 1


if __name__ == "__main__":
    raise SystemExit(main())
