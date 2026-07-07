"""Benchmark — Obsidia pre-inference routing vs direct-to-model baseline.

For each task family:
  - obsidia: full pipeline (IR -> gates -> topic -> level decision)
  - baseline: what a classic agent does — send everything to the remote model

Outputs route accuracy, remote calls avoided, tokens saved, and per-task
traces to results/benchmark_report.json.

Modes:
  python benchmarks/run_benchmark.py                  baseline tokens estimated
  python benchmarks/run_benchmark.py --live-baseline  baseline REALLY sent to
      Fireworks (all 18 tasks, real tokens, real request_ids) for a measured
      head-to-head: raw model vs the full Obsidia stack. Requires
      FIREWORKS_API_KEY and spends real credits on the cheapest ladder model.

Obsidia-side Fireworks calls happen only when FIREWORKS_API_KEY is set;
otherwise level-3 tasks are recorded as dry runs with token estimates.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.adapters import fireworks  # noqa: E402
from app.adapters.fireworks import estimate_tokens  # noqa: E402
from app.cli import load_memory_index, run_one  # noqa: E402
from app.metrics.collector import MetricsCollector  # noqa: E402
from app.router.decision import DEFAULT_MODEL_LADDER  # noqa: E402


def main() -> int:
    live_baseline = "--live-baseline" in sys.argv
    tasks = json.loads((ROOT / "benchmarks" / "tasks.json").read_text(encoding="utf-8"))
    memory_index = load_memory_index()
    metrics = MetricsCollector()
    ladder = fireworks.allowed_models() or DEFAULT_MODEL_LADDER
    baseline_model = ladder[0]

    rows, correct = [], 0
    baseline_tokens = baseline_calls = 0
    baseline_latency = 0.0
    baseline_errors: list[str] = []

    for task in tasks:
        t0 = time.perf_counter()
        decision = run_one(task["request"], metrics, memory_index)
        routing_latency = round(time.perf_counter() - t0, 4)

        ok = decision["route"] == task["expected_route"]
        correct += ok
        baseline_calls += 1
        if live_baseline:
            # Classic-agent arm: the raw request goes straight to the model.
            b = fireworks.chat(baseline_model, task["request"])
            baseline_tokens += b["total_tokens"]
            baseline_latency += b["latency_s"]
            if b.get("error"):
                baseline_errors.append(f"{task['id']}: {b['error']}")
        else:
            baseline_tokens += estimate_tokens(task["request"])

        rows.append({
            "id": task["id"],
            "expected_route": task["expected_route"],
            "actual_route": decision["route"],
            "route_correct": ok,
            "level": decision["level"],
            "model": decision["model"],
            "gate": decision["gate"]["verdict"],
            "routing_latency_s": routing_latency,
        })
        mark = "OK " if ok else "FAIL"
        print(f"[{mark}] {task['id']:<24} -> {decision['route']}")

    summary = metrics.summary()
    report = {
        "route_accuracy": round(correct / len(tasks), 3),
        "obsidia": summary,
        "baseline_direct_model": {
            "mode": "live" if live_baseline else "estimated",
            "model": baseline_model if live_baseline else None,
            "remote_calls": baseline_calls,
            "tokens": baseline_tokens,
            "total_latency_s": round(baseline_latency, 3) if live_baseline else None,
            "errors": baseline_errors,
        },
        "tasks": rows,
    }
    out = ROOT / "results" / "benchmark_report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    errors = [r for r in metrics.records if r.get("error")]
    live_calls = summary["fireworks_calls"]

    print()
    print(f"route accuracy        : {report['route_accuracy']:.0%} ({correct}/{len(tasks)})")
    print(f"remote calls: baseline {baseline_calls} -> obsidia {summary['fireworks_needed']}")
    if live_baseline:
        saved = baseline_tokens - summary["fireworks_tokens"]
        pct = saved / baseline_tokens if baseline_tokens else 0
        print(f"MEASURED tokens: baseline {baseline_tokens} -> obsidia "
              f"{summary['fireworks_tokens']} (saved {saved}, {pct:.0%})")
        if baseline_errors:
            print(f"baseline errors       : {len(baseline_errors)}")
            for e in baseline_errors:
                print(f"  - {e}")
    else:
        print(f"estimated tokens saved: {summary['estimated_tokens_saved']}")
    print(f"level-0 rate          : {summary['level0_rate']:.0%}")
    if live_calls and not errors:
        print(f"fireworks LIVE        : {live_calls} calls OK, "
              f"{summary['fireworks_tokens']} real tokens, "
              f"avg latency {summary['avg_latency_s']}s")
    elif errors:
        print(f"fireworks ERRORS      : {len(errors)} call(s) failed")
        for r in errors:
            print(f"  - {r.get('model')}: {r['error']}")
    else:
        print("fireworks             : dry-run (no FIREWORKS_API_KEY)")
    print(f"report -> {out}")
    return 0 if correct == len(tasks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
