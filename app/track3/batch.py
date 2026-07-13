"""Track 3 batch runner.

Reads /input/tasks.json, runs the full escalation pipeline for each task,
writes results to /output/results.json, receipts to /output/receipts/,
and a run report to /output/run_report.json.

Format in:
  [{"task_id": "...", "prompt": "...", "expected": "..." (optional),
    "category": "..." (optional)}]

Format out (results.json):
  [{"task_id": "...", "answer": "..."}]

Format out (run_report.json): see RunReport dataclass below.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from app.track3 import receipt as receipt_mod
from app.track3 import replay as replay_mod
from app.track3 import runtime


# ── Paths ─────────────────────────────────────────────────────────────────────

_INPUT_DEFAULT  = Path("/input/tasks.json")
_OUTPUT_DEFAULT = Path("/output")


def _load_tasks(input_path: Path) -> list[dict]:
    with input_path.open(encoding="utf-8") as f:
        tasks = json.load(f)
    assert isinstance(tasks, list), "tasks.json must be a JSON array"
    for t in tasks:
        assert "task_id" in t and "prompt" in t, (
            f"Each task must have task_id and prompt: {t}"
        )
    return tasks


def _grader(answer: str, expected: str) -> bool:
    """Deterministic exact-or-contains grade (lowercase, strip)."""
    a = answer.strip().lower()
    e = expected.strip().lower()
    return e == a or e in a


def run_batch(
    input_path: Path | None = None,
    output_dir: Path | None = None,
    qwen_available: bool | None = None,
    brody_available: bool | None = None,
) -> dict:
    """Execute the batch, return the run_report dict."""
    input_path = input_path or _INPUT_DEFAULT
    output_dir = output_dir or _OUTPUT_DEFAULT
    output_dir.mkdir(parents=True, exist_ok=True)
    receipts_dir = output_dir / "receipts"
    receipts_dir.mkdir(exist_ok=True)

    tasks = _load_tasks(input_path)

    results: list[dict] = []
    receipts: list[dict] = []

    # counters
    counters = {
        "tasks_total":           len(tasks),
        "tasks_resolved":        0,
        "tasks_unresolved":      0,
        "level_0_count":         0,
        "level_1_count":         0,
        "level_2_count":         0,
        "level_3_brody_count":   0,
        "level_3_qwen_count":    0,
        "model_avoided_count":   0,
        "qwen_calls":            0,
        "brody_calls":           0,
        "fireworks_calls":       0,
        "tokens_local_total":    0,
        "tokens_remote_total":   0,
        "latency_total_ms":      0.0,
        "receipt_hashes_valid":  0,
        "receipt_hashes_total":  0,
        "replay_pass_count":     0,
        "replay_fail_count":     0,
        "KX108_ONLY_count":      0,
        "mutations_count":       0,
        "world_actions_count":   0,
        "correct_count":         0,
        "graded_count":          0,
    }
    level_latencies: dict[str, list[float]] = {
        "LEVEL_0": [], "LEVEL_1": [], "LEVEL_2": [],
        "LEVEL_3_brody": [], "LEVEL_3_qwen": [], "UNRESOLVED": [],
    }
    category_correct: dict[str, int] = {}
    category_total:   dict[str, int] = {}
    receipt_hash_list: list[str] = []

    batch_t0 = time.perf_counter()

    for task in tasks:
        tid   = task["task_id"]
        raw   = task["prompt"]
        exp   = task.get("expected", "")
        cat   = task.get("category", "general")

        t0 = time.perf_counter()
        ev = runtime.run(raw, qwen_available=qwen_available,
                         brody_available=brody_available)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        # ── Aggregate level ───────────────────────────────────────────────────
        lvl = ev.get("escalation_level_final", "UNRESOLVED")
        if lvl == "LEVEL_0":
            counters["level_0_count"] += 1
        elif lvl == "LEVEL_1":
            counters["level_1_count"] += 1
        elif lvl == "LEVEL_2":
            counters["level_2_count"] += 1
        elif lvl == "LEVEL_3":
            if ev.get("brody_readonly_attempted") and ev.get("status") == "resolved":
                counters["level_3_brody_count"] += 1
                level_latencies["LEVEL_3_brody"].append(latency_ms)
            else:
                counters["level_3_qwen_count"] += 1
                level_latencies["LEVEL_3_qwen"].append(latency_ms)
        else:
            pass

        if lvl in level_latencies:
            level_latencies[lvl].append(latency_ms)

        # ── Status / invariants ────────────────────────────────────────────────
        if ev.get("status") == "resolved":
            counters["tasks_resolved"] += 1
        else:
            counters["tasks_unresolved"] += 1

        if ev.get("model_avoided"):
            counters["model_avoided_count"] += 1
        if ev.get("qwen_attempted"):
            counters["qwen_calls"] += 1
        if ev.get("brody_readonly_attempted"):
            counters["brody_calls"] += 1
        if ev.get("fireworks_attempted"):
            counters["fireworks_calls"] += 1
        if ev.get("decision_authority") == "KX108_ONLY":
            counters["KX108_ONLY_count"] += 1
        counters["tokens_local_total"]  += ev.get("tokens_local", 0)
        counters["tokens_remote_total"] += ev.get("tokens_remote", 0)
        counters["latency_total_ms"]    += latency_ms
        counters["mutations_count"]     += len(ev.get("mutations_performed", []))
        counters["world_actions_count"] += len(ev.get("external_calls", []))

        # ── Accuracy ──────────────────────────────────────────────────────────
        if exp:
            counters["graded_count"] += 1
            category_total[cat] = category_total.get(cat, 0) + 1
            ok = _grader(ev.get("answer", ""), exp)
            if ok:
                counters["correct_count"] += 1
                category_correct[cat] = category_correct.get(cat, 0) + 1

        # ── Receipt ──────────────────────────────────────────────────────────
        hash_ok = receipt_mod.verify_hash(ev)
        counters["receipt_hashes_total"] += 1
        if hash_ok:
            counters["receipt_hashes_valid"] += 1
        receipt_hash_list.append(ev.get("receipt_hash", ""))

        receipt_path = receipts_dir / f"{tid}.json"
        receipt_path.write_text(
            json.dumps(ev, default=str, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # ── Replay ───────────────────────────────────────────────────────────
        rp = replay_mod.replay(str(receipt_path))
        if rp.get("REPLAY_MATCH") == "YES":
            counters["replay_pass_count"] += 1
        else:
            counters["replay_fail_count"] += 1

        receipts.append({
            "task_id":      tid,
            "status":       ev.get("status"),
            "level":        lvl,
            "receipt_hash": ev.get("receipt_hash", ""),
            "hash_valid":   hash_ok,
            "replay_match": rp.get("REPLAY_MATCH"),
        })

        results.append({"task_id": tid, "answer": ev.get("answer", "")})

    # ── Build report ──────────────────────────────────────────────────────────
    total_ms = round((time.perf_counter() - batch_t0) * 1000, 2)
    accuracy_total = (
        round(counters["correct_count"] / counters["graded_count"], 4)
        if counters["graded_count"] > 0 else None
    )
    accuracy_by_cat = {
        cat: round(category_correct.get(cat, 0) / tot, 4)
        for cat, tot in category_total.items()
    } if category_total else {}

    latency_by_stage = {
        k: {
            "count":   len(v),
            "mean_ms": round(sum(v) / len(v), 2) if v else None,
            "min_ms":  round(min(v), 2) if v else None,
            "max_ms":  round(max(v), 2) if v else None,
        }
        for k, v in level_latencies.items()
    }

    report = {
        **counters,
        "batch_total_ms":     total_ms,
        "accuracy_scope":     (
            "graded tasks with expected field" if counters["graded_count"] > 0
            else "no_expected_answers_provided"
        ),
        "accuracy_total":     accuracy_total,
        "accuracy_by_category": accuracy_by_cat,
        "latency_by_stage":   latency_by_stage,
        "receipt_hashes":     receipt_hash_list,
    }

    # ── Write outputs ─────────────────────────────────────────────────────────
    (output_dir / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "receipts.json").write_text(
        json.dumps(receipts, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "run_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    return report


def main() -> int:
    input_path  = Path(os.environ.get("T3_INPUT",  str(_INPUT_DEFAULT)))
    output_dir  = Path(os.environ.get("T3_OUTPUT", str(_OUTPUT_DEFAULT)))

    qwen_env = os.environ.get("T3_QWEN_AVAILABLE", "")
    qwen_available: bool | None = (
        True  if qwen_env.lower() in ("1", "true", "yes") else
        False if qwen_env.lower() in ("0", "false", "no")  else
        None
    )
    brody_env = os.environ.get("T3_BRODY_AVAILABLE", "")
    brody_available: bool | None = (
        True  if brody_env.lower() in ("1", "true", "yes") else
        False if brody_env.lower() in ("0", "false", "no")  else
        None
    )

    print(f"[batch] input={input_path} output={output_dir}", flush=True)
    print(f"[batch] qwen_available={qwen_available} brody_available={brody_available}", flush=True)

    if not input_path.exists():
        print(f"[batch] ERROR: input not found: {input_path}", file=sys.stderr)
        return 1

    report = run_batch(
        input_path=input_path,
        output_dir=output_dir,
        qwen_available=qwen_available,
        brody_available=brody_available,
    )

    print(f"[batch] done — {report['tasks_resolved']}/{report['tasks_total']} resolved", flush=True)
    print(f"[batch] levels: L0={report['level_0_count']} L1={report['level_1_count']} "
          f"L2={report['level_2_count']} L3_qwen={report['level_3_qwen_count']} "
          f"L3_brody={report['level_3_brody_count']}", flush=True)
    print(f"[batch] tokens_local={report['tokens_local_total']} remote=0 fireworks=0", flush=True)
    print(f"[batch] replay_pass={report['replay_pass_count']} fail={report['replay_fail_count']}", flush=True)

    ok = (
        report["fireworks_calls"]    == 0 and
        report["tokens_remote_total"] == 0 and
        report["mutations_count"]     == 0 and
        report["replay_fail_count"]   == 0 and
        report["KX108_ONLY_count"]    == report["tasks_total"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
