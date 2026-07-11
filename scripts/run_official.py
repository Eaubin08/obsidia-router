"""Official AMD Track 1 runner -- slim, no benchmark phases.

Reads  /input/tasks.json   (or --input <path>)
Writes /output/results.json (or --output <path>)

Output format: [{"task_id": "...", "answer": "..."}, ...]

LOT H: every task is resolved by the single canonical authority
benchmarks/official_resolver.resolve_task(). This file only handles CLI,
I/O, the 600 s global budget and the strict output projection — it holds
NO routing or escalation logic of its own.

FIREWORKS_API_KEY never logged or written.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

from app.metrics.triage_metrics import triage_summary
from benchmarks.official_resolver import (
    default_context,
    project_official_row,
    resolve_task,
)


def _parse_args() -> tuple[Path, Path]:
    args = sys.argv[1:]
    input_path = Path("/input/tasks.json")
    output_path = Path("/output/results.json")
    if "--input" in args:
        input_path = Path(args[args.index("--input") + 1])
    if "--output" in args:
        output_path = Path(args[args.index("--output") + 1])
    return input_path, output_path


def main() -> int:
    input_path, output_path = _parse_args()

    if not input_path.exists():
        print(f"ERROR: tasks file not found: {input_path}", file=sys.stderr)
        return 2

    raw = input_path.read_text(encoding="utf-8")
    try:
        raw_tasks = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in {input_path}: {exc}", file=sys.stderr)
        return 2

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Canonical context: 600 s global deadline, 30 s output reserve,
    # ALLOWED_MODELS honoured (fallback ladder only when absent).
    ctx = default_context(with_deadline=True)

    api_key_present = bool(os.environ.get("FIREWORKS_API_KEY", "").strip())
    print("obsidia-router official runner")
    print(f"  tasks      : {len(raw_tasks)}")
    print(f"  fireworks  : {'configured' if api_key_present else 'dry-run (no FIREWORKS_API_KEY)'}")
    print(f"  model set  : {ctx.model_set_status}")
    print(f"  input      : {input_path}")
    print(f"  output     : {output_path}")
    print()

    results: list[dict] = []
    resolutions: list[dict] = []
    tokens_total = 0
    remote_calls = 0
    budget_error = False

    for task in raw_tasks:
        task_id = task.get("task_id") or task.get("id") or f"unknown_{len(results)}"
        try:
            res = resolve_task(task, ctx)
        except TimeoutError as exc:
            # Controlled budget exhaustion: fail loudly, never a silent
            # partial file presented as complete.
            print(f"ERROR: {exc}", file=sys.stderr)
            budget_error = True
            break
        except Exception as exc:
            res = {
                "task_id": task_id,
                "answer": f"[error] routing failed: {type(exc).__name__}: {exc}",
                "route": "error", "total_tokens": 0, "remote_calls": 0,
                "latency_s": 0.0,
            }
        results.append(project_official_row(res))
        resolutions.append({k: v for k, v in res.items()
                            if k not in ("answer",)})
        tokens_total += res.get("total_tokens", 0)
        remote_calls += res.get("remote_calls", 0)
        print(f"  [{task_id}] route={res.get('route')} "
              f"tok={res.get('total_tokens', 0)} "
              f"{res.get('latency_s', 0.0) * 1000:.1f}ms")

    if budget_error:
        return 3

    # AMD-required output: strict [{"task_id","answer"}] list only.
    output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Audit-only companion (metadata, no prompt/answer content beyond the
    # resolution fields), never read by the AMD harness.
    triage_path = output_path.parent / "track1_triage_receipts.json"
    triage_path.write_text(
        json.dumps(
            {"tasks": resolutions,
             "summary": triage_summary(ctx.metrics.records)},
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print(f"results    -> {output_path}")
    print(f"triage     -> {triage_path}")
    print(f"tasks      : {len(results)}")
    print(f"tokens used: {tokens_total}")
    print(f"remote calls: {remote_calls}/{len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
