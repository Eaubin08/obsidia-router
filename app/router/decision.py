"""Inference-level decision — the heart of Obsidia Router.

Given the IR (structure), the gate verdict (frame) and the topic (semantics),
decide deterministically WHETHER a model is needed at all, and if so, which
level:

  Level 0  NO_MODEL   — status, HOLD, deny, clarification, commands-only
  Level 1  BRODY      — local proprietary LLM organ (stubbed in this cut)
  Level 2  MEMORY     — corpus lookup, no generation
  Level 3  FIREWORKS  — remote escalation, cheapest sufficient model

Classic agents route between models. Obsidia first decides if a model is
necessary.
"""
from __future__ import annotations

from app.gates.gates import evaluate as evaluate_gates
from app.ir.unified_ir import build_ir
from app.router.semantic_topics import route_topic

# Fireworks serverless model ladder, cheapest first (verified against the
# live /v1/models catalog). The catalog moves fast: override via
# ALLOWED_MODELS (comma-separated) to match the current library or the
# scoring harness allowlist, ordered cheapest first.
DEFAULT_MODEL_LADDER = [
    "accounts/fireworks/models/gpt-oss-120b",
    "accounts/fireworks/models/glm-5p1",
    "accounts/fireworks/models/deepseek-v4-pro",
]


def _complexity_score(ir: dict, raw: str) -> int:
    """Deterministic proxy for task complexity. Picks the ladder rung."""
    score = 0
    if ir["intent_type"] == "code_request":
        score += 1
    if len(raw) > 400:
        score += 1
    return min(score, 2)


def decide(raw: str, memory_index: dict | None = None,
           model_ladder: list[str] | None = None) -> dict:
    """Full deterministic pre-inference pipeline for one request."""
    ladder = model_ladder or DEFAULT_MODEL_LADDER
    ir = build_ir(raw)
    gate = evaluate_gates(ir)
    topic = route_topic(raw)

    decision: dict = {
        "ir": ir,
        "gate": gate,
        "topic": topic,
        "level": 0,
        "route": None,
        "model": None,
        "reason": None,
    }

    # --- Level 0: the frame decides, no token spent -------------------------
    if gate["verdict"] == "DENY":
        decision.update(route="denied", reason=gate["reason"])
        return decision
    if gate["verdict"] == "HOLD":
        decision.update(route="hold_commands_only", reason=gate["reason"])
        return decision
    if gate["verdict"] == "CLARIFY":
        # A canonical topic covered by the corpus resolves the ambiguity
        # without inference; otherwise clarification is cheaper than a model.
        if memory_index is not None and topic["is_canonical"]:
            entry = memory_index.get(topic["topic"])
            if entry:
                decision.update(level=2, route="memory_hit",
                                reason=f"ambiguous phrasing but canonical topic {topic['topic']} covered by corpus")
                decision["memory_entry"] = entry
                return decision
        decision.update(route="clarification_needed",
                        reason="missing: " + ", ".join(ir["missing"]))
        return decision
    if ir["intent_type"] == "status":
        decision.update(route="no_model_needed",
                        reason="status is answered from local structure")
        return decision
    if topic["topic"] == "IR_REQUEST":
        decision.update(route="no_model_needed",
                        reason="translation to structured intent is the router's own job")
        return decision

    # --- Level 2: memory before generation -----------------------------------
    if memory_index is not None and topic["is_canonical"]:
        entry = memory_index.get(topic["topic"])
        if entry:
            decision.update(level=2, route="memory_hit",
                            reason=f"canonical topic {topic['topic']} covered by corpus")
            decision["memory_entry"] = entry
            return decision

    # --- Level 1: local proprietary organ -------------------------------------
    if ir["intent_type"] == "question" and not ir["needs"]["remote_model"]:
        decision.update(level=1, route="brody",
                        reason="semantic production on an already-structured request; local organ suffices")
        return decision

    # --- Level 3: justified remote escalation ---------------------------------
    rung = _complexity_score(ir, raw)
    rung = min(rung, len(ladder) - 1)
    decision.update(level=3, route="fireworks", model=ladder[rung],
                    reason=f"remote inference required; cheapest sufficient rung {rung}")
    return decision
