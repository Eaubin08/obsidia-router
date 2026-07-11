"""LOT G4 — evidence-based model selection benchmark (Track 1).

Compares three strategies on the exact 8 practice tasks of
submission/track1/input/practice_tasks.json:

  STRATEGY A — DIRECT SINGLE MODEL : one model answers all 8 tasks.
  STRATEGY B — DIRECT ADAPTIVE     : the measured best model per category.
  STRATEGY C — OBSIDIA FINAL       : verified local closure first, bounded
                                     Fireworks escalation only when the local
                                     answer fails the deterministic grader.

Grading: PRACTICE_DETERMINISTIC_GRADER — keyword/regex proxy, same style as
benchmarks/answer_accuracy.py, adapted to the practice_tasks.json prompts.
Never presented as the hidden AMD judge score.

All remote calls go through app.adapters.fireworks (FIREWORKS_BASE_URL,
never a hardcoded key/URL) with the bounded evaluation timeout (60 s) and
the evaluation capture ceiling. Answers are graded in memory then dropped;
persisted artifacts are metadata-only.

Usage (live, spends tokens):
  python -m benchmarks.model_selection_matrix --out-dir <dir>
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.adapters import fireworks  # noqa: E402
from app.cli import load_memory_index, run_one  # noqa: E402
from app.metrics.collector import MetricsCollector  # noqa: E402
from app.router.decision import DEFAULT_MODEL_LADDER  # noqa: E402

PRACTICE_TASKS_PATH = ROOT / "submission" / "track1" / "input" / "practice_tasks.json"

# Evaluation ceiling: 8192 verified for gpt-oss-120b (LOT G2 smoke test).
# For other ladder models no per-model ceiling is registered; 8192 is used
# as the bounded, documented evaluation ceiling (standard OpenAI-compatible
# request field) and flagged as such in the artifacts.
EVAL_MAX_TOKENS = 8192
EVAL_TIMEOUT_S = 60.0

GRADER_LABEL = "PRACTICE_DETERMINISTIC_GRADER"

# ── Deterministic graders for the practice_tasks.json prompts ─────────────────
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

_GRADERS_BY_ID = {tid: (cat, checks) for tid, cat, checks in PRACTICE_GRADERS}


def load_practice_tasks() -> list[dict]:
    """Stable mapping task_id / category / prompt from practice_tasks.json."""
    raw = json.loads(PRACTICE_TASKS_PATH.read_text(encoding="utf-8"))
    tasks = []
    for t in raw:
        tid = t["task_id"]
        cat, _ = _GRADERS_BY_ID[tid]
        tasks.append({"task_id": tid, "category": cat, "prompt": t["prompt"]})
    return tasks


def grade_answer(task_id: str, answer: str) -> dict:
    """PRACTICE_DETERMINISTIC_GRADER — regex ALL-match, same doctrine as
    benchmarks/answer_accuracy.py (dry-run and [error] outputs always fail)."""
    cat, checks = _GRADERS_BY_ID[task_id]
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


# ── Direct model matrix (STRATEGY A raw material) ─────────────────────────────

def run_model_on_task(model: str, task: dict) -> dict:
    """One direct call: raw prompt, no system prompt, temperature 0.0,
    evaluation ceiling + bounded extended timeout. Metadata-only result;
    the answer is graded in memory and dropped."""
    r = fireworks.chat(
        model, task["prompt"],
        max_tokens=EVAL_MAX_TOKENS,
        timeout=EVAL_TIMEOUT_S,
        allow_extended_timeout=True,
    )
    answer = r.get("text", "") if not r.get("error") else ""
    g = grade_answer(task["task_id"], answer)
    return {
        "model": model,
        "task_id": task["task_id"],
        "category": task["category"],
        "selected_model": model,
        "actual_model_used": r.get("model", model),
        "requested_max_tokens": EVAL_MAX_TOKENS,
        "requested_timeout_seconds": EVAL_TIMEOUT_S,
        "prompt_tokens": r.get("prompt_tokens", 0),
        "completion_tokens": r.get("completion_tokens", 0),
        "total_tokens": r.get("total_tokens", 0),
        "latency_s": r.get("latency_s", 0.0),
        "finish_reason": r.get("finish_reason"),
        "final_content_present": r.get("final_content_present"),
        "reasoning_content_present": r.get("reasoning_content_present"),
        "truncated": r.get("truncated", False),
        "error": r.get("error"),
        "transport_error_type": (
            "network" if r.get("error", "").startswith("network")
            else ("http" if str(r.get("error", "")).startswith("HTTP") else None)
        ) if r.get("error") else None,
        "answer_chars": len(answer),
        "grade": g["grade"],
        "pass": g["pass"],
        "failure_reason": g["failure_reason"],
        "format_compliant": g["format_compliant"],
    }


def run_full_matrix(models: list[str], tasks: list[dict]) -> list[dict]:
    rows = []
    for mi, model in enumerate(models):
        for task in tasks:
            row = run_model_on_task(model, task)
            row["model_index"] = mi
            rows.append(row)
            print(f"  [{model.split('/')[-1]}] {task['task_id']} "
                  f"grade={row['grade']} tok={row['total_tokens']} "
                  f"lat={row['latency_s']}s err={row['error']}")
    return rows


# ── Per-model metrics & rankings ──────────────────────────────────────────────

def model_metrics(rows: list[dict], model: str) -> dict:
    mrows = [r for r in rows if r["model"] == model]
    n = len(mrows)
    passed = sum(1 for r in mrows if r["pass"])
    clean = (
        all(not r["error"] for r in mrows)
        and all(not r["truncated"] for r in mrows)
    )
    return {
        "model": model,
        "tasks": n,
        "passed_tasks": passed,
        "accuracy_rate": round(passed / n, 4) if n else 0.0,
        "format_compliance_rate": round(
            sum(1 for r in mrows if r["format_compliant"]) / n, 4) if n else 0.0,
        "timeouts": sum(1 for r in mrows
                        if r["transport_error_type"] == "network"),
        "truncations": sum(1 for r in mrows if r["truncated"]),
        "errors": sum(1 for r in mrows if r["error"]),
        "prompt_tokens": sum(r["prompt_tokens"] for r in mrows),
        "completion_tokens": sum(r["completion_tokens"] for r in mrows),
        "total_tokens": sum(r["total_tokens"] for r in mrows),
        "average_tokens_per_task": round(
            sum(r["total_tokens"] for r in mrows) / n, 1) if n else 0.0,
        "total_latency_s": round(sum(r["latency_s"] for r in mrows), 3),
        "average_latency_s": round(
            sum(r["latency_s"] for r in mrows) / n, 3) if n else 0.0,
        "maximum_latency_s": max(
            (r["latency_s"] for r in mrows), default=0.0),
        "strict_8_of_8": passed == n == 8,
        "clean_run": clean,
    }


def rank_models(metrics: list[dict]) -> list[dict]:
    """1. accuracy desc; 2. format compliance desc; 3. total tokens asc;
    4. total latency asc."""
    return sorted(metrics, key=lambda m: (
        -m["accuracy_rate"], -m["format_compliance_rate"],
        m["total_tokens"], m["total_latency_s"]))


def best_single_model(metrics: list[dict]) -> str | None:
    """Passes gate (8/8 strict), zero error/truncation/timeout, then lowest
    total tokens, latency tiebreak. None if no model qualifies."""
    eligible = [m for m in metrics
                if m["strict_8_of_8"] and m["errors"] == 0
                and m["truncations"] == 0 and m["timeouts"] == 0]
    if not eligible:
        return None
    eligible.sort(key=lambda m: (m["total_tokens"], m["total_latency_s"]))
    return eligible[0]["model"]


def category_winners(rows: list[dict]) -> dict[str, dict]:
    """Per category: passed + format compliant + no timeout/truncation,
    minimum tokens, latency tiebreak."""
    winners: dict[str, dict] = {}
    cats = {r["category"] for r in rows}
    for cat in sorted(cats):
        candidates = [
            r for r in rows
            if r["category"] == cat and r["pass"] and r["format_compliant"]
            and not r["truncated"] and not r["error"]
        ]
        if not candidates:
            winners[cat] = {"category": cat, "winning_model": None,
                            "reason": "no_model_passed"}
            continue
        candidates.sort(key=lambda r: (r["total_tokens"], r["latency_s"]))
        w = candidates[0]
        winners[cat] = {
            "category": cat,
            "winning_model": w["model"],
            "tokens": w["total_tokens"],
            "latency_s": w["latency_s"],
            "grade": w["grade"],
            "reason": "min_tokens_among_passing",
        }
    return winners


# ── STRATEGY C — Obsidia final ────────────────────────────────────────────────

def run_obsidia_on_task(task: dict, memory_index: dict,
                        winners: dict[str, dict]) -> dict:
    """Official Obsidia path (run_one), graded; on local FAIL, one bounded
    escalation to the task's CATEGORY_WINNER (study-only). No retry."""
    metrics = MetricsCollector()
    t0 = time.perf_counter()
    decision = run_one(task["prompt"], metrics, memory_index)
    latency = round(time.perf_counter() - t0, 4)

    rec = metrics.records[-1] if metrics.records else {}
    route = decision["route"]
    output = decision.get("output") or ""
    tokens = rec.get("fireworks_tokens", 0)
    prompt_tok = rec.get("prompt_tokens", 0)
    comp_tok = rec.get("completion_tokens", 0)
    remote_calls = 1 if (route == "fireworks" and not rec.get("dry_run")) else 0

    g = grade_answer(task["task_id"], output)
    local_pass = g["pass"] and remote_calls == 0
    escalated = False
    selected_model = rec.get("actual_model_used") if remote_calls else None

    if not g["pass"]:
        # local (or first remote) answer failed the grader — one bounded
        # escalation to the measured category winner (study only).
        winner = winners.get(task["category"], {}).get("winning_model")
        if winner:
            r = fireworks.chat(
                winner, task["prompt"],
                max_tokens=EVAL_MAX_TOKENS,
                timeout=EVAL_TIMEOUT_S,
                allow_extended_timeout=True,
            )
            escalated = True
            remote_calls += 1
            selected_model = winner
            tokens += r.get("total_tokens", 0)
            prompt_tok += r.get("prompt_tokens", 0)
            comp_tok += r.get("completion_tokens", 0)
            latency = round(latency + r.get("latency_s", 0.0), 4)
            answer = r.get("text", "") if not r.get("error") else ""
            g = grade_answer(task["task_id"], answer)

    return {
        "task_id": task["task_id"],
        "category": task["category"],
        "route": route,
        "level": decision["level"],
        "local_solver_used": route == "local_solver",
        "memory_used": route == "memory_hit",
        "brody_used": route == "brody",
        "fireworks_used": remote_calls > 0,
        "selected_model": selected_model,
        "remote_calls": remote_calls,
        "escalated_to_category_winner": escalated,
        "prompt_tokens": prompt_tok,
        "completion_tokens": comp_tok,
        "total_tokens": tokens,
        "latency_s": latency,
        "answer_grade": g["grade"],
        "pass": g["pass"],
        "failure_reason": g["failure_reason"],
        "local_closure": local_pass,
        "remote_inference_required": not local_pass,
    }


# ── Strategy aggregation ──────────────────────────────────────────────────────

def strategy_summary(name: str, rows: list[dict],
                     token_key: str = "total_tokens") -> dict:
    return {
        "strategy": name,
        "answers": len(rows),
        "accuracy": sum(1 for r in rows if r["pass"]),
        "remote_calls": sum(r.get("remote_calls", 1) for r in rows),
        "prompt_tokens": sum(r.get("prompt_tokens", 0) for r in rows),
        "completion_tokens": sum(r.get("completion_tokens", 0) for r in rows),
        "total_tokens": sum(r.get(token_key, 0) for r in rows),
        "total_latency_s": round(sum(r.get("latency_s", 0.0) for r in rows), 3),
    }


def main() -> int:
    out_dir = None
    if "--out-dir" in sys.argv:
        out_dir = Path(sys.argv[sys.argv.index("--out-dir") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)

    ladder = fireworks.allowed_models()
    model_set_status = "OFFICIAL_RUNTIME_ALLOWLIST"
    if ladder is None:
        ladder = list(DEFAULT_MODEL_LADDER)
        model_set_status = "NON_OFFICIAL_FALLBACK_LADDER"

    tasks = load_practice_tasks()
    print(f"model set     : {model_set_status}")
    print(f"models        : {ladder}")
    print(f"tasks         : {len(tasks)}")
    print(f"max calls     : {len(ladder) * len(tasks)} (matrix) + escalations")
    print()

    # Phase 5 — full matrix
    print("== MODEL MATRIX ==")
    matrix_rows = run_full_matrix(ladder, tasks)

    # Phase 6/7/8
    metrics_per_model = [model_metrics(matrix_rows, m) for m in ladder]
    ranking = rank_models(metrics_per_model)
    best_single = best_single_model(metrics_per_model)
    winners = category_winners(matrix_rows)

    # STRATEGY A rows = best single model's matrix rows (8 tasks, remote_calls=1 each)
    strategy_a_rows = (
        [dict(r, remote_calls=1) for r in matrix_rows if r["model"] == best_single]
        if best_single else [])

    # STRATEGY B rows = per-category winner's matrix row
    strategy_b_rows = []
    for cat, w in winners.items():
        if w.get("winning_model"):
            row = next(r for r in matrix_rows
                       if r["model"] == w["winning_model"]
                       and r["category"] == cat)
            strategy_b_rows.append(dict(row, remote_calls=1))

    # Phase 9 — STRATEGY C
    print()
    print("== OBSIDIA FINAL ==")
    memory_index = load_memory_index()
    strategy_c_rows = []
    for task in tasks:
        row = run_obsidia_on_task(task, memory_index, winners)
        strategy_c_rows.append(row)
        print(f"  {task['task_id']} route={row['route']} "
              f"grade={row['answer_grade']} local={row['local_closure']} "
              f"remote_calls={row['remote_calls']} tok={row['total_tokens']}")

    # Phase 10 — comparison
    comp = {
        "strategy_a_direct_single": strategy_summary(
            "DIRECT_SINGLE_MODEL", strategy_a_rows),
        "strategy_b_direct_adaptive": strategy_summary(
            "DIRECT_ADAPTIVE_ORACLE", strategy_b_rows),
        "strategy_c_obsidia_final": strategy_summary(
            "OBSIDIA_ADAPTIVE_FINAL", strategy_c_rows),
    }
    a_tok = comp["strategy_a_direct_single"]["total_tokens"]
    b_tok = comp["strategy_b_direct_adaptive"]["total_tokens"]
    c_tok = comp["strategy_c_obsidia_final"]["total_tokens"]
    comp["obsidia_tokens_saved_vs_single"] = a_tok - c_tok
    comp["obsidia_saving_rate_vs_single"] = (
        round((a_tok - c_tok) / a_tok, 4) if a_tok else None)
    comp["obsidia_tokens_saved_vs_adaptive"] = b_tok - c_tok
    comp["obsidia_saving_rate_vs_adaptive"] = (
        round((b_tok - c_tok) / b_tok, 4) if b_tok else None)
    comp["remote_calls_avoided"] = 8 - comp[
        "strategy_c_obsidia_final"]["remote_calls"]
    comp["local_verified_closures"] = sum(
        1 for r in strategy_c_rows if r["local_closure"])
    comp["remote_required_categories"] = [
        r["category"] for r in strategy_c_rows
        if r["remote_inference_required"]]

    # Phase 11 — per-task verdicts
    verdicts = []
    for task in tasks:
        cat = task["category"]
        w = winners.get(cat, {})
        c_row = next(r for r in strategy_c_rows if r["category"] == cat)
        best_tok = w.get("tokens")
        if c_row["local_closure"]:
            winner_v = "OBSIDIA_LOCAL"
            reason = "verified local closure at 0 Fireworks tokens"
        elif c_row["pass"]:
            winner_v = "OBSIDIA_REMOTE"
            reason = "local closure failed; governed escalation passed"
        elif w.get("winning_model"):
            winner_v = "DIRECT_MODEL"
            reason = "Obsidia final failed grader; a direct model passed"
        else:
            winner_v = "NO_VALID_RESULT"
            reason = "no strategy passed this category"
        verdicts.append({
            "category": cat,
            "best_direct_model": w.get("winning_model"),
            "best_direct_tokens": best_tok,
            "obsidia_local_pass": c_row["local_closure"],
            "obsidia_remote_required": c_row["remote_inference_required"],
            "obsidia_selected_model": c_row["selected_model"],
            "obsidia_tokens": c_row["total_tokens"],
            "winner": winner_v,
            "reason": reason,
        })

    report = {
        "grader": GRADER_LABEL,
        "model_set_status": model_set_status,
        "models": ladder,
        "eval_max_tokens": EVAL_MAX_TOKENS,
        "eval_timeout_seconds": EVAL_TIMEOUT_S,
        "matrix_rows": matrix_rows,
        "model_metrics": metrics_per_model,
        "ranking": [m["model"] for m in ranking],
        "best_single_model": best_single,
        "category_winners": winners,
        "strategy_comparison": comp,
        "per_task_verdicts": verdicts,
        "obsidia_rows": strategy_c_rows,
        "hidden_amd_judge": "UNKNOWN — never anticipated by this study",
    }

    if out_dir:
        (out_dir / "model_matrix_metadata.json").write_text(
            json.dumps({"grader": GRADER_LABEL, "rows": matrix_rows,
                        "model_metrics": metrics_per_model},
                       indent=2), encoding="utf-8")
        (out_dir / "category_winners.json").write_text(
            json.dumps(winners, indent=2), encoding="utf-8")
        (out_dir / "strategy_comparison.json").write_text(
            json.dumps(comp, indent=2), encoding="utf-8")
        (out_dir / "obsidia_final_evaluation.json").write_text(
            json.dumps({"rows": strategy_c_rows, "verdicts": verdicts},
                       indent=2), encoding="utf-8")
        (out_dir / "model_matrix_report.md").write_text(
            _render_md(report), encoding="utf-8")
        print(f"\nartifacts -> {out_dir}")

    print()
    print(json.dumps(comp, indent=2))
    return 0


def _render_md(report: dict) -> str:
    lines = [
        "# LOT G4 — Model selection matrix (PRACTICE_DETERMINISTIC_GRADER)",
        "",
        f"Model set: {report['model_set_status']}",
        f"Best single model: {report['best_single_model']}",
        "",
        "| Model | Acc | Tokens | Latency s | Errors | Trunc |",
        "|---|---|---|---|---|---|",
    ]
    for m in report["model_metrics"]:
        lines.append(
            f"| {m['model'].split('/')[-1]} | {m['passed_tasks']}/8 "
            f"| {m['total_tokens']} | {m['total_latency_s']} "
            f"| {m['errors']} | {m['truncations']} |")
    lines += ["", "Hidden AMD judge: UNKNOWN.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
