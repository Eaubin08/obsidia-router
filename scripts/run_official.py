"""Official AMD Track 1 runner -- slim, no benchmark phases.

Reads  /input/tasks.json   (or --input <path>)
Writes /output/results.json (or --output <path>)

Output format: [{"task_id": "...", "answer": "..."}, ...]

Parity with run_benchmark.py --track1-official:
  - same bounded Fireworks profile (max_tokens + system prompt via contract)
  - same model selection (ALLOWED_MODELS respected via select_model_preference)
  - same brody stub escalation gate (no BRODY_ENDPOINT -> bounded Fireworks)
  - same clarification escalation gate (hidden task, no expected_route -> bounded Fireworks)
  - same FIREWORKS_BASE_URL pass-through via app.adapters.fireworks
  - no benchmark phases, no REPORT.md, no benchmark_report.json, no receipts
  - FIREWORKS_API_KEY never logged or written
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.adapters import fireworks
from app.cli import load_memory_index, run_one
from app.metrics.collector import MetricsCollector
from app.router.decision import DEFAULT_MODEL_LADDER
from app.router.model_triage import select_model_for_request
from app.metrics.triage_metrics import triage_summary
from benchmarks.track1_remote_answer_contract import build_remote_answer_contract
from benchmarks.track1_runner import normalize_task, track1_answer
from benchmarks.track1_escalation_guard import (
    should_escalate_clarification_to_fireworks,
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


def _build_track1_profile(request: str, task_id: str, allowed_models: list[str]) -> dict:
    """Build the bounded Fireworks contract identical to the official benchmark path.

    Mirrors run_benchmark.py lines 1165-1176:
      _contract = build_remote_answer_contract(request)
      _t1_profile = {max_tokens, system, model, remote_answer_contract}

    "model" is informative telemetry only (LOT D) — the model actually
    called is decided centrally by select_model_for_request() inside
    decide() / the escalation block below.
    """
    contract = build_remote_answer_contract(request, allowed_models=allowed_models)
    return {
        "max_tokens": contract["max_tokens"],
        "system":     contract["contract_prompt"],
        "model":      contract["model_preference"],
        "remote_answer_contract": contract,
    }


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

    tasks = [normalize_task(t) for t in raw_tasks]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    memory_index = load_memory_index()
    metrics = MetricsCollector()
    ladder = fireworks.allowed_models() or DEFAULT_MODEL_LADDER

    api_key_present = bool(os.environ.get("FIREWORKS_API_KEY", "").strip())
    print("obsidia-router official runner")
    print(f"  tasks      : {len(tasks)}")
    print(f"  fireworks  : {'configured' if api_key_present else 'dry-run (no FIREWORKS_API_KEY)'}")
    print(f"  input      : {input_path}")
    print(f"  output     : {output_path}")
    print()

    results: list[dict] = []
    triage_rows: list[dict] = []
    tokens_total = 0
    remote_calls = 0

    for task in tasks:
        task_id = task.get("id") or task.get("task_id") or f"unknown_{len(results)}"
        request = task.get("request") or task.get("prompt") or ""
        answer = "[error] no request"
        tok = 0
        route_label = "error"
        latency_ms = 0.0

        try:
            t0 = time.perf_counter()

            # Build bounded Fireworks contract for every task.
            # Mirrors the official benchmark: all hidden AMD tasks default to
            # "fireworks" when expected_route is absent (task.get("expected_route","fireworks")=="fireworks").
            # The profile is silently ignored by run_one() for locally-closed routes.
            t1_profile = _build_track1_profile(request, task_id, ladder)

            decision = run_one(request, metrics, memory_index, ladder,
                               track1_profile=t1_profile)

            # ── Escalation gate (mirrors run_benchmark.py lines 1192-1210) ───
            # Hidden AMD tasks have no expected_route, so every brody stub and
            # every clarification_needed must escalate to Fireworks to avoid a
            # placeholder that scores 0 on answer accuracy.
            _needs_escalation = (
                (decision["route"] == "brody"
                 and not os.environ.get("BRODY_ENDPOINT"))
                or should_escalate_clarification_to_fireworks(
                    task, request, decision)
            )
            if _needs_escalation:
                _c = build_remote_answer_contract(request, allowed_models=ladder)
                # LOT D: same single triage authority as decide()'s own
                # level-3 escalation — the contract's model_preference is
                # informative only and never selects the call target here.
                _sel = select_model_for_request(
                    request, ladder, answer_kind=_c["answer_kind"],
                )
                _model = _sel["selected_model"]
                _fw = fireworks.chat(
                    _model, request,
                    max_tokens=_c["max_tokens"],
                    system=_c["contract_prompt"],
                )
                decision.update(
                    route="fireworks",
                    level=3,
                    model=_model,
                    actual_model_used=_model,
                    output=_fw["text"],
                )
                if metrics.records:
                    # LOT E: this record was created by run_one() BEFORE
                    # escalation (route was "brody"/"clarification_needed"),
                    # so every triage field must be patched here too — not
                    # just the model — or aggregates would silently miss
                    # every escalated call.
                    _last = metrics.records[-1]
                    _last["route"] = "fireworks"
                    _last["fireworks_tokens"] = _fw.get("total_tokens", 0)
                    _last["prompt_tokens"] = _fw.get("prompt_tokens", 0)
                    _last["completion_tokens"] = _fw.get("completion_tokens", 0)
                    _last["remote_call_avoided"] = False
                    _last["selected_model"] = _model
                    _last["selected_rung"] = _sel["selected_rung"]
                    _last["selection_reason"] = _sel["selection_reason"]
                    _last["ladder_size"] = len(ladder)
                    _last["contract_model_preference"] = _c["model_preference"]
                    _last["actual_model_used"] = _model
                    _last["raw_prompt_chars"] = len(request)
                    _last["system_prompt_chars"] = len(_c["contract_prompt"])
                    _last["compression_applied"] = False

            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            rec = metrics.records[-1] if metrics.records else {}
            tok = rec.get("fireworks_tokens", 0)
            tokens_total += tok
            if decision["route"] == "fireworks":
                remote_calls += 1

            row = {
                "id":                   task_id,
                "request":              request,
                "actual_route":         decision["route"],
                "gate_verdict":         decision["gate"]["verdict"],
                "gate_matched":         decision["gate"].get("matched"),
                "level":                decision["level"],
                "model":                decision["model"],
                "intent_type":          decision["ir"]["intent_type"],
                "target_layer":         decision["ir"]["target_layer"],
                "missing":              decision["ir"].get("missing", []),
                "fireworks_tokens":     tok,
                "remote_call_avoided":  rec.get("remote_call_avoided", True),
                "routing_latency_ms":   latency_ms,
                "output":               decision.get("output", ""),
                "memory_entry":         decision.get("memory_entry"),
                "topic_name":           decision.get("topic", {}).get("topic", "general"),
                # LOT E — audit-only triage evidence, never part of the
                # required AMD schema (see results.json below, untouched).
                "selected_model":       rec.get("selected_model"),
                "selected_rung":        rec.get("selected_rung"),
                "selection_reason":     rec.get("selection_reason"),
                "ladder_size":          rec.get("ladder_size"),
                "contract_model_preference": rec.get("contract_model_preference"),
                "actual_model_used":    rec.get("actual_model_used"),
                "raw_prompt_chars":     rec.get("raw_prompt_chars"),
                "system_prompt_chars":  rec.get("system_prompt_chars"),
            }
            answer = track1_answer(row)
            route_label = decision["route"]
            # Metadata-only sidecar: never duplicate the request,
            # generated answer, memory content, or system-prompt content.
            triage_rows.append({
                "id": task_id,
                "actual_route": decision["route"],
                "gate_verdict": decision["gate"]["verdict"],
                "gate_matched": decision["gate"].get("matched"),
                "level": decision["level"],
                "intent_type": decision["ir"]["intent_type"],
                "target_layer": decision["ir"]["target_layer"],
                "selected_model": rec.get("selected_model"),
                "selected_rung": rec.get("selected_rung"),
                "selection_reason": rec.get("selection_reason"),
                "ladder_size": rec.get("ladder_size"),
                "contract_model_preference": rec.get(
                    "contract_model_preference"
                ),
                "actual_model_used": rec.get("actual_model_used"),
                "raw_prompt_chars": rec.get("raw_prompt_chars"),
                "system_prompt_chars": rec.get("system_prompt_chars"),
                "compression_applied": rec.get("compression_applied"),
                "compressed_prompt_chars": rec.get(
                    "compressed_prompt_chars"
                ),
                "fireworks_tokens": rec.get("fireworks_tokens", 0),
                "prompt_tokens": rec.get("prompt_tokens", 0),
                "completion_tokens": rec.get("completion_tokens", 0),
                "remote_call_avoided": rec.get(
                    "remote_call_avoided", True
                ),
                "routing_latency_ms": latency_ms,
            })

        except Exception as exc:
            answer = f"[error] routing failed: {type(exc).__name__}: {exc}"

        results.append({"task_id": task_id, "answer": answer})
        print(f"  [{task_id}] route={route_label} tok={tok} {latency_ms:.1f}ms")

    # AMD-required output: strict [{"task_id","answer"}] list only. This
    # schema is never touched by LOT E.
    output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # LOT E — audit-only companion file, next to results.json, never read
    # by the AMD harness (which only opens the exact --output path). Gives
    # a reviewer the "why" behind each remote call without touching the
    # required schema.
    triage_path = output_path.parent / "track1_triage_receipts.json"
    triage_path.write_text(
        json.dumps(
            {"tasks": triage_rows, "summary": triage_summary(metrics.records)},
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
