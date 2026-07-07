"""Cognitive value inputs — readonly projection over EXISTING metrics.

Groups fields already computed by the benchmark into the inputs a governed
cognitive-value ledger (the valuation layer of the full Obsidia stack,
deliberately deferred, non-token by policy) would read.

Hard rules, enforced by tests:
  - no new score, no aggregate, no proxy — every numeric value is copied
    verbatim from the benchmark report;
  - no mint, no wallet, no blockchain, no economic scoring;
  - stdlib only, no import from the private stack;
  - this projection influences nothing: not the routing, not the gates,
    not the Track 1 metrics. decision_authority stays KX108_ONLY.
"""
from __future__ import annotations

# The only keys this projection is allowed to emit (whitelist, tested).
ALLOWED_GROUPS = {
    "avoided_inference", "frame_stability", "time_cost", "control", "boundary",
}

BOUNDARY = {
    "projection": "readonly",
    "mint": False,
    "wallet": False,
    "blockchain": False,
    "economic_scoring": False,
    "decision_authority": "KX108_ONLY",
    "status": "DEFERRED — inputs only; valuation layer lives upstream",
}


def cognitive_value_inputs(report: dict) -> dict:
    """Regroup existing benchmark report fields. Computes nothing new."""
    s = report["obsidia"]
    b = report["baseline_direct_model"]
    g = report["governance"]
    d = report["dynamic"]
    lat = report["latency"]

    gate_distribution: dict[str, int] = {}
    for row in report["tasks"]:
        gate_distribution[row["gate"]] = gate_distribution.get(row["gate"], 0) + 1

    return {
        "avoided_inference": {
            "tokens_baseline": b["tokens"],
            "tokens_obsidia": s["fireworks_tokens"],
            "estimated_tokens_saved": s["estimated_tokens_saved"],
            "remote_calls_avoided": s["remote_calls_avoided"],
            "level0_rate": s["level0_rate"],
        },
        "frame_stability": {
            "baseline_violations": g["baseline_violations"],
            "obsidia_violations": g["obsidia_violations"],
            "governed_tasks": g["governed_tasks"],
            "invariants_held_rate": d["invariants_held_rate"],
        },
        "time_cost": {
            "avg_routing_ms_local": lat["avg_routing_ms_local"],
            "avg_fireworks_call_s": lat["avg_fireworks_call_s"],
        },
        "control": {
            "route_accuracy": report["route_accuracy"],
            "gate_verdict_distribution": gate_distribution,
        },
        "boundary": dict(BOUNDARY),
    }
