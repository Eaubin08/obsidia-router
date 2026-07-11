"""Path / speed / escalation quality axes for the benchmark.

No global quality score is produced here.
This module only regroups existing per-task benchmark facts:
expected route, actual route, level, gate, model, tokens and latency.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any


def _route(row: dict[str, Any]) -> str | None:
    return row.get("actual_route") or row.get("route")


def _latency_ms(row: dict[str, Any]) -> float:
    return float(row.get("routing_latency_s", 0.0) or 0.0) * 1000.0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return ordered[idx]


def _stats(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"n": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    return {
        "n": len(values),
        "avg": round(statistics.mean(values), 3),
        "p50": round(statistics.median(values), 3),
        "p95": round(_percentile(values, 95), 3),
        "p99": round(_percentile(values, 99), 3),
        "max": round(max(values), 3),
    }


def _group_latency(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if key == "route":
            k = _route(row)
        else:
            k = row.get(key)
        grouped[str(k)].append(_latency_ms(row))
    return {k: _stats(v) for k, v in sorted(grouped.items())}


def quality_axes(report: dict[str, Any]) -> dict[str, Any]:
    """Return separate quality axes, not a single composite score."""

    rows = list(report.get("tasks", []))
    total = len(rows)

    route_matches = sum(1 for row in rows if row.get("expected_route") == _route(row))
    route_correct_true = sum(1 for row in rows if row.get("route_correct") is True)
    exact_route_matches = sum(1 for row in rows if row.get("exact_route_match") is True)
    accepted_route_matches = sum(1 for row in rows if row.get("accepted_route_correct") is True)
    alternative_route_uses = sum(1 for row in rows if row.get("alternative_route_used") is True)

    level0 = [row for row in rows if row.get("level") == 0]
    level1_2 = [row for row in rows if row.get("level") in (1, 2)]
    hold_deny_clarify = [row for row in rows if row.get("gate") in {"HOLD", "DENY", "CLARIFY"}]
    world_actions = [row for row in rows if row.get("intent_type") == "world_action"]
    fireworks_rows = [row for row in rows if _route(row) == "fireworks"]

    def model_or_token(row: dict[str, Any]) -> bool:
        return bool(row.get("model")) or int(row.get("fireworks_tokens", 0) or 0) > 0

    expected_fireworks = sum(1 for row in rows if row.get("expected_route") == "fireworks")
    actual_fireworks = len(fireworks_rows)

    local_ms = report.get("latency", {}).get("avg_routing_ms_local", 0.0) or 0.0
    remote_s = report.get("latency", {}).get("avg_fireworks_call_s", 0.0) or 0.0
    remote_local_ratio = round((remote_s * 1000.0) / local_ms, 1) if local_ms else None

    tokens_on_fireworks = sum(int(row.get("fireworks_tokens", 0) or 0) for row in fireworks_rows)
    tokens_off_fireworks = sum(
        int(row.get("fireworks_tokens", 0) or 0)
        for row in rows
        if _route(row) != "fireworks"
    )

    return {
        "route_quality": {
            "tasks": total,
            "route_matches": route_matches,
            "exact_route_matches": exact_route_matches,
            "route_correct_true": route_correct_true,
            "accepted_route_matches": accepted_route_matches,
            "alternative_route_uses": alternative_route_uses,
            "route_accuracy": report.get("route_accuracy"),
        },
        "path_quality": {
            "level0_tasks": len(level0),
            "level0_model_leaks": sum(1 for row in level0 if model_or_token(row)),
            "hold_deny_clarify_tasks": len(hold_deny_clarify),
            "hold_deny_clarify_model_leaks": sum(1 for row in hold_deny_clarify if model_or_token(row)),
            "world_action_tasks": len(world_actions),
            "world_action_model_leaks": sum(1 for row in world_actions if model_or_token(row)),
            "level1_2_tasks": len(level1_2),
            "level1_2_fireworks_token_leaks": sum(
                1 for row in level1_2 if int(row.get("fireworks_tokens", 0) or 0) > 0
            ),
        },
        "escalation_quality": {
            "fireworks_expected": expected_fireworks,
            "fireworks_actual": actual_fireworks,
            "unnecessary_fireworks_calls": sum(
                1 for row in rows
                if _route(row) != "fireworks" and model_or_token(row)
            ),
            "fireworks_only_on_allow": sum(1 for row in fireworks_rows if row.get("gate") == "ALLOW"),
            "level0_fireworks_token_leaks": sum(
                1 for row in level0 if int(row.get("fireworks_tokens", 0) or 0) > 0
            ),
            "tokens_on_fireworks_rows": tokens_on_fireworks,
            "tokens_off_fireworks_rows": tokens_off_fireworks,
        },
        "speed_profile": {
            "by_level_ms": _group_latency(rows, "level"),
            "by_route_ms": _group_latency(rows, "route"),
            "remote_local_latency_ratio": remote_local_ratio,
            "dynamic_avg_decision_ms": report.get("dynamic", {}).get("avg_decision_ms"),
            "dynamic_decisions_per_second": report.get("dynamic", {}).get("decisions_per_second"),
        },
        "note": "Separate axes only: no global quality score, no value score, no scoring impact.",
    }
