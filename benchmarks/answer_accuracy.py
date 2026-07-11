"""Answer accuracy by category — canonical resolver on the 8 OFFICIAL practice tasks.

LOT H: this benchmark no longer owns a parallel resolution pipeline. Every
task is resolved by benchmarks/official_resolver.resolve_task() — the same
single authority used by scripts/run_official.py and the Docker CMD — then
graded by the shared PRACTICE_DETERMINISTIC_GRADER
(benchmarks/practice_grading.py) on the exact prompts of
submission/track1/input/practice_tasks.json.

Honest doctrine: "8/8 practice answers passed" is NOT the same claim as
"8 generic local solvers validated". A local closure only counts when the
answer is zero-token AND passes the grader. Categories that genuinely need
Fireworks are reported as remote — never forced local.

Usage (live, spends tokens for remote categories):
    python benchmarks/answer_accuracy.py
Writes:
  results/answer_accuracy_by_category.json  (legacy format, UNCHANGED)
  results/amd_practice_category_metrics.json (per-category detail)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks.official_resolver import default_context, resolve_task  # noqa: E402
from benchmarks.practice_grading import (  # noqa: E402
    GRADER_LABEL,
    _extract_code_block,  # noqa: F401 — re-export (tests import it here)
    grade_answer,
    load_practice_tasks,
)


def main() -> int:
    api_available = bool(os.environ.get("FIREWORKS_API_KEY", "").strip())
    ctx = default_context()
    tasks = load_practice_tasks()

    category_entries: list[dict] = []
    by_cat: dict = {}

    print(f"API available: {api_available}  (canonical resolver — same path as Docker)")
    print(f"model set    : {ctx.model_set_status}")
    print(f"{'Category':<20} {'Task':<13} {'Grade':<6} {'Route':<22} "
          f"{'Tokens':>7} {'Local?':<7} Solver")
    print("-" * 100)

    for task in tasks:
        res = resolve_task(task, ctx)
        g = grade_answer(task["task_id"], res["answer"])

        ok = g["pass"]
        zero_token = res["total_tokens"] == 0
        local_verified = zero_token and ok and res["remote_calls"] == 0

        entry = {
            "category": task["category"],
            "task_id": task["task_id"],
            "grade": g["grade"],
            "route": res["route"],
            "level": res["level"],
            "model": res["selected_model"],
            "tokens": res["total_tokens"],
            "prompt_tokens": res["prompt_tokens"],
            "completion_tokens": res["completion_tokens"],
            "latency_s": res["latency_s"],
            "answer_excerpt": res["answer"][:120],
            "local_solver": res["local_solver_name"],
            "local_candidate_valid": res["local_candidate_valid"],
            "local_verified_closure": local_verified,
            "remote_actual": res["remote_calls"] > 0,
            "remote_calls": res["remote_calls"],
            "zero_token": zero_token,
            "accuracy_status": g["grade"],
            "failure_reason": g["failure_reason"],
            "grader": GRADER_LABEL,
            "resolver": "benchmarks.official_resolver.resolve_task",
        }
        category_entries.append(entry)
        by_cat.setdefault(task["category"], []).append(ok)

        print(f"{task['category']:<20} {task['task_id']:<13} {g['grade']:<6} "
              f"{res['route']:<22} {res['total_tokens']:>7} "
              f"{'yes' if local_verified else 'no':<7} "
              f"{res['local_solver_name'] or '-'}")

    n = len(tasks)
    local_pass_count = sum(
        1 for e in category_entries if e["local_verified_closure"])
    remote_count = sum(1 for e in category_entries if e["remote_actual"])
    total_tokens = sum(e["tokens"] for e in category_entries)
    tokens_by_cat = {e["category"]: e["tokens"] for e in category_entries}

    frontier = {
        "amd_practice_tasks": n,
        "verified_local_closure_count": local_pass_count,
        "verified_local_closure_rate": round(local_pass_count / n, 4),
        "verified_local_closure_rate_label": (
            f"{local_pass_count}/{n} = {local_pass_count / n:.1%} "
            "(zero-token AND grade=PASS)"
        ),
        "remote_actual_count": remote_count,
        "remote_actual_rate": f"{remote_count}/{n} = {remote_count / n:.1%}",
        "total_tokens_amd_practice": total_tokens,
        "tokens_by_category": tokens_by_cat,
        "task_source": "submission/track1/input/practice_tasks.json",
        "resolver": "benchmarks.official_resolver.resolve_task (canonical)",
        "honesty_note": (
            "8/8 graded answers is a different claim from 8 generic local "
            "solvers; categories genuinely requiring Fireworks are reported "
            "as remote."
        ),
        "api_readiness_run": {
            "api_available": api_available,
            "dry_run_mode": not api_available,
            "doctrine": (
                "Obsidia can call Fireworks. It simply does not call Fireworks "
                "when the request is already closed by structure, local solvers, "
                "canonical readonly knowledge, or governance gates."
            ),
        },
    }

    print()
    print("-- Zero-token frontier (AMD practice 8 official tasks) -------------")
    print(f"  verified_local_closure_rate : {frontier['verified_local_closure_rate_label']}")
    print(f"  remote_actual_rate          : {frontier['remote_actual_rate']}")
    print(f"  total_tokens_amd            : {total_tokens}")
    print(f"  api_available               : {api_available}")
    print("  tokens by category:")
    for c, tok in tokens_by_cat.items():
        note = "  <- remote" if tok > 0 else "  (local)"
        print(f"    {c:<24}: {tok:>6}{note}")

    summary = {cat: {"passed": sum(v), "total": len(v)} for cat, v in by_cat.items()}
    total_ok = sum(s["passed"] for s in summary.values())
    legacy_payload = {
        "answer_accuracy_by_category": summary,
        "overall": {"passed": total_ok, "total": n,
                    "rate": round(total_ok / n, 4)},
        "grading": "keyword_proxy_local (hidden set is LLM-judged)",
    }
    out1 = ROOT / "results" / "answer_accuracy_by_category.json"
    out1.write_text(json.dumps(legacy_payload, indent=2), encoding="utf-8")

    out2 = ROOT / "results" / "amd_practice_category_metrics.json"
    out2.write_text(json.dumps({
        "generated_by": "benchmarks/answer_accuracy.py",
        "grading": "keyword_proxy_local (hidden set is LLM-judged)",
        "grader": GRADER_LABEL,
        "resolver": "benchmarks.official_resolver.resolve_task",
        "categories": category_entries,
        "zero_token_frontier_amd": frontier,
    }, indent=2), encoding="utf-8")

    status = "8/8 PASS" if total_ok == n else f"{total_ok}/{n} — DEGRADED"
    print(f"\noverall: {total_ok}/{n}  accuracy_status={status}")
    print(f"  Note: results reflect {'live API' if api_available else 'dry-run (no API key)'} mode")
    print(f"-> {out1}")
    print(f"-> {out2}")
    return 0 if total_ok == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
