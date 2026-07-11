"""Metrics collector — every decision is accounted for.

Track 1 metrics: fireworks_calls, fireworks_tokens, latency, accuracy hooks.
Obsidia metrics: no_model_needed, brody_needed, memory_hits, hold, denied,
clarification_needed, commands_only, remote_calls_avoided,
estimated_tokens_saved, invariants respected.

LOT E: adaptive model triage evidence (selected_model/selected_rung/
selection_reason/...) and its aggregates — see app.metrics.triage_metrics
for the doctrine (local routes carry no triage evidence; rung position
classes are mutually exclusive; no token/dollar savings are derived from
rung position).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from app.adapters.fireworks import estimate_tokens
from app.metrics.triage_metrics import triage_summary

_LEVEL0_ROUTES = {
    "no_model_needed", "hold_commands_only", "denied", "clarification_needed",
}

# Fields with no truthful value on a non-remote record: always None there
# (see app.metrics.triage_metrics module docstring — "local-route records
# carry no triage evidence"). "selected_model" is deliberately sourced from
# decision["model"] (the single triage authority's output field, LOT D) —
# there is no separate decision["selected_model"] key.
_TRIAGE_FIELDS_FROM_SAME_KEY = (
    "selected_rung", "selection_reason", "ladder_size",
    "contract_model_preference", "actual_model_used",
    "raw_prompt_chars", "system_prompt_chars",
)


class MetricsCollector:
    def __init__(self) -> None:
        self.records: list[dict] = []
        self.started = time.time()

    def record(self, raw: str, decision: dict, result: dict | None = None) -> dict:
        route = decision["route"]
        is_remote = route == "fireworks"
        rec = {
            "input_chars": len(raw),
            "route": route,
            "level": decision["level"],
            "intent_type": decision["ir"]["intent_type"],
            "model": decision.get("model"),
            "gate_verdict": decision["gate"]["verdict"],
            "invariants": decision["gate"]["invariants"],
            "fireworks_tokens": 0,
            "latency_s": 0.0,
            "remote_call_avoided": route != "fireworks",
            "estimated_tokens_saved": 0 if route == "fireworks" else estimate_tokens(raw),
            # LOT E — doctrine: None on every local route, real value only
            # when a genuine remote selection happened.
            "compression_applied": False if is_remote else None,
            "compressed_prompt_chars": None,
        }
        rec["selected_model"] = decision.get("model") if is_remote else None
        for field in _TRIAGE_FIELDS_FROM_SAME_KEY:
            rec[field] = decision.get(field) if is_remote else None
        if result is not None:
            rec["fireworks_tokens"] = result.get("total_tokens", 0)
            rec["prompt_tokens"] = result.get("prompt_tokens", 0)
            rec["completion_tokens"] = result.get("completion_tokens", 0)
            rec["finish_reason"] = result.get("finish_reason")
            rec["final_content_present"] = result.get(
                "final_content_present"
            )
            rec["reasoning_content_present"] = result.get(
                "reasoning_content_present"
            )
            rec["truncated"] = result.get("truncated", False)
            rec["remote_response_error"] = result.get("error")
            rec["latency_s"] = result.get("latency_s", 0.0)
            rec["dry_run"] = result.get("dry_run", False)
            if result.get("error"):
                rec["error"] = result["error"]
        self.records.append(rec)
        return rec

    def summary(self) -> dict:
        routes = [r["route"] for r in self.records]
        base = {
            "total_tasks": len(self.records),
            "no_model_needed": routes.count("no_model_needed"),
            "commands_only_hold": routes.count("hold_commands_only"),
            "denied": routes.count("denied"),
            "clarification_needed": routes.count("clarification_needed"),
            "memory_hits": routes.count("memory_hit"),
            "brody_needed": routes.count("brody"),
            "fireworks_needed": routes.count("fireworks"),
            "fireworks_calls": sum(1 for r in self.records
                                   if r["route"] == "fireworks" and not r.get("dry_run", True)),
            "fireworks_tokens": sum(r["fireworks_tokens"] for r in self.records),
            "remote_calls_avoided": sum(1 for r in self.records if r["remote_call_avoided"]),
            "estimated_tokens_saved": sum(r["estimated_tokens_saved"] for r in self.records),
            "avg_latency_s": round(
                sum(r["latency_s"] for r in self.records) / len(self.records), 4
            ) if self.records else 0.0,
            "level0_rate": round(
                sum(1 for r in self.records if r["route"] in _LEVEL0_ROUTES)
                / len(self.records), 3
            ) if self.records else 0.0,
        }
        # LOT E: adaptive model triage aggregates, merged flat into the same
        # summary dict (see app.metrics.triage_metrics for every doctrine
        # and the zero-division-safe, zero-remote-calls-safe guarantees).
        base.update(triage_summary(self.records))
        return base

    def export(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"summary": self.summary(), "records": self.records},
            indent=2, ensure_ascii=False), encoding="utf-8")
        return path
