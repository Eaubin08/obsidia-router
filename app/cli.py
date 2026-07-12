"""Obsidia Router demo CLI.

Usage:
  python -m app.cli "your request"          one-shot, prints the full trace
  python -m app.cli                         interactive loop
  python -m app.cli --json "your request"   machine-readable output

Every request prints the deterministic pre-inference trace:
intent / layer / action / risk / needs / gate / level / route / model /
tokens spent vs avoided.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.adapters import brody_stub, fireworks
from app.ir.unified_ir import format_ir
from app.metrics.collector import MetricsCollector
from app.router.decision import decide

MEMORY_INDEX_PATH = Path(__file__).resolve().parent.parent / "examples" / "memory_index.json"


def load_memory_index() -> dict:
    if MEMORY_INDEX_PATH.exists():
        return json.loads(MEMORY_INDEX_PATH.read_text(encoding="utf-8"))
    return {}


def run_one(raw: str, metrics: MetricsCollector, memory_index: dict,
            ladder: list[str] | None = None,
            track1_profile: dict | None = None) -> dict:
    """Route one request through the Obsidia pre-inference pipeline.

    track1_profile, when provided, overrides the default Fireworks call with
    a bounded Track 1 response budget: {"max_tokens": int, "system": str, "profile": str}.
    Only active in --track1-official mode; transparent to V3B and demo modes.
    """
    decision = decide(raw, memory_index=memory_index,
                      model_ladder=ladder or fireworks.allowed_models())
    result = None
    output_text = None

    if decision["route"] == "fireworks":
        # LOT D: the model is decided once, centrally, by decide() (see
        # app.router.model_triage.select_model_for_request). track1_profile
        # only supplies max_tokens/system; its "model" field (the contract's
        # calibrated default) is informative telemetry only and must never
        # override the router's selection.
        _fw_model = decision["model"]
        decision["actual_model_used"] = _fw_model
        # LOT E: raw_prompt_chars/system_prompt_chars are lengths only, never
        # the prompt content. contract_model_preference is the contract's
        # informative field (LOT D), kept distinct from the real selection.
        decision["raw_prompt_chars"] = len(raw)
        if track1_profile:
            decision["system_prompt_chars"] = len(track1_profile["system"])
            decision["contract_model_preference"] = track1_profile.get("model")
            result = fireworks.chat(
                _fw_model, raw,
                max_tokens=track1_profile["max_tokens"],
                system=track1_profile["system"],
            )
        else:
            decision["system_prompt_chars"] = None
            decision["contract_model_preference"] = None
            result = fireworks.chat(_fw_model, raw)
        output_text = result["text"]
        decision["finish_reason"] = result.get("finish_reason")
        decision["final_content_present"] = result.get(
            "final_content_present"
        )
        decision["reasoning_content_present"] = result.get(
            "reasoning_content_present"
        )
        decision["truncated"] = result.get("truncated", False)
        decision["remote_response_error"] = result.get("error")
    elif decision["route"] == "local_solver":
        output_text = decision["solver_answer"]
    elif decision["route"] == "brody":
        output_text = brody_stub.answer(decision["ir"], decision["topic"])["text"]
    elif decision["route"] == "memory_hit":
        output_text = decision["memory_entry"]
    elif decision["route"] == "no_model_needed":
        output_text = format_ir(decision["ir"])
    elif decision["route"] == "hold_commands_only":
        output_text = ("HOLD — world action detected. Nothing was executed. "
                       "Invariants: no_auto_act, no_auto_commit, no_auto_push. "
                       "Ask for a commands-only plan to review and run yourself.")
    elif decision["route"] == "clarification_needed":
        output_text = "CLARIFY — " + decision["reason"]
    elif decision["route"] == "denied":
        output_text = "DENIED — " + decision["reason"]

    metrics.record(raw, decision, result)
    decision["output"] = output_text
    return decision


def print_trace(decision: dict) -> None:
    ir, gate = decision["ir"], decision["gate"]
    print("-" * 62)
    print(format_ir(ir))
    print(f"  topic       : {decision['topic']['topic']}")
    print(f"  gate        : {gate['verdict']} ({gate['reason']})")
    print(f"  level       : {decision['level']}  route: {decision['route']}")
    print(f"  model       : {decision['model'] or 'none — no remote inference'}")
    print(f"  reason      : {decision['reason']}")
    print("-" * 62)
    print(decision["output"])


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    args = [a for a in argv if a != "--json"]
    metrics = MetricsCollector()
    memory_index = load_memory_index()

    if args:
        decision = run_one(" ".join(args), metrics, memory_index)
        if as_json:
            printable = {k: v for k, v in decision.items() if k != "memory_entry"}
            print(json.dumps(printable, indent=2, ensure_ascii=False, default=str))
        else:
            print_trace(decision)
            print()
            print("metrics:", json.dumps(metrics.summary(), ensure_ascii=False))
        return 0

    print("Obsidia Router — semantic routing before inference. Ctrl-C to quit.")
    try:
        while True:
            raw = input("\n> ").strip()
            if not raw:
                continue
            if raw in {"quit", "exit"}:
                break
            if raw == "metrics":
                print(json.dumps(metrics.summary(), indent=2, ensure_ascii=False))
                continue
            print_trace(run_one(raw, metrics, memory_index))
    except (KeyboardInterrupt, EOFError):
        pass
    out = metrics.export("results/session_metrics.json")
    print(f"\nmetrics exported → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
