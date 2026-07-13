"""ActivePlan — structured execution plan derived deterministically from UnifiedInputIR.

No inference needed to produce this plan. It is a pure function of the IR.
It describes what to do; the runtime decides how.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.ir.unified_ir import build_ir


def _requested_outcome(ir: dict) -> str:
    intent = ir["intent_type"]
    layer = ir["target_layer"]
    _intent_map = {
        "world_action":  "commands-only plan — no auto-execution",
        "status":        "structural status answer from local state",
        "code_request":  "bounded code answer from local solver or local model",
        "audit":         "bounded read-only audit answer",
        "plan":          "step-by-step bounded plan",
        "reasoning":     "bounded reasoning answer",
        "question":      "factual or contextual answer",
        "unknown":       "clarification required before any action",
    }
    outcome = _intent_map.get(intent, "bounded answer")
    if layer not in ("unknown", "world", "system"):
        outcome += f" [{layer} layer]"
    return outcome


def _required_capabilities(ir: dict) -> list[str]:
    intent = ir["intent_type"]
    needs  = ir.get("needs", {})
    missing = ir.get("missing", [])

    if "intent" in missing or intent == "unknown":
        return ["clarify"]

    if intent == "world_action":
        return ["hold"]

    caps: list[str] = []

    if intent == "status":
        caps.append("structural_answer")

    if intent in ("question", "plan", "audit"):
        caps.extend(["structural_answer", "deterministic_factual"])

    if intent == "reasoning":
        caps.extend(["deterministic_math", "deterministic_factual", "local_qwen"])

    if intent == "code_request":
        caps.extend(["deterministic_code", "local_qwen"])

    # Brody/memory hints → local model fallback (Brody engine is not connected)
    if needs.get("brody") or needs.get("memory"):
        if "local_qwen" not in caps:
            caps.append("local_qwen")

    # Any open question that isn't closed by deterministic caps → Qwen
    if intent == "question" and "local_qwen" not in caps:
        caps.append("local_qwen")

    if not caps:
        caps.extend(["structural_answer", "local_qwen"])

    return list(dict.fromkeys(caps))  # stable deduplicate


def _execution_mode(ir: dict) -> str:
    intent = ir["intent_type"]
    if intent == "world_action":
        return "commands_only"
    if intent == "unknown" or "intent" in ir.get("missing", []):
        return "clarify"
    if intent in ("code_request", "reasoning"):
        return "local_solver_then_qwen"
    if intent in ("question", "audit", "plan"):
        return "local_solver_then_qwen"
    return "local_only"


def build(raw: str, ir: dict | None = None) -> dict:
    """Build an ActivePlan from a raw request and its pre-built IR.

    If ir is None it is computed here (cheap — pure regex, no network).
    """
    if ir is None:
        ir = build_ir(raw)

    return {
        "request_id":             str(uuid.uuid4()),
        "intent_type":            ir["intent_type"],
        "requested_outcome":      _requested_outcome(ir),
        "required_capabilities":  _required_capabilities(ir),
        "risk_level":             ir["risk_level"],
        "world_action_requested": ir["intent_type"] == "world_action",
        "needs_clarification":    "intent" in ir.get("missing", []),
        "selected_execution_mode": _execution_mode(ir),
        "constraints":            ir.get("constraints", []),
        "created_at":             datetime.now(timezone.utc).isoformat(),
    }
