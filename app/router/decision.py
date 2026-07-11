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
from app.router.local_solvers import try_local_solvers
from app.router.model_triage import select_model_for_request
from app.router.semantic_topics import route_topic

# Fallback ladder used only when ALLOWED_MODELS is not provided (see
# app.adapters.fireworks.allowed_models(), the single parsing authority).
# Order preserved as configured here; it is NOT independently verified as
# cost-ascending against the live Fireworks catalog. Call this a calibrated
# fallback ladder, not a proven "cheapest first" ordering — the harness's
# ALLOWED_MODELS (ordered by the scoring harness itself) is the authority
# whenever it is provided.
DEFAULT_MODEL_LADDER = [
    "accounts/fireworks/models/gpt-oss-120b",
    "accounts/fireworks/models/glm-5p1",
    "accounts/fireworks/models/deepseek-v4-pro",
]


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

    # --- Stack-layer pre-routing (before CLARIFY) ----------------------------
    # Governed surfaces have deterministic routes and must never hit CLARIFY.
    # DENY/HOLD are still respected first (below).
    if ir["target_layer"] == "obsidure" and gate["verdict"] not in ("DENY", "HOLD"):
        decision.update(level=1, route="obsidure_route_only",
                        reason="obsidure layer: proposal-only routing, non-sovereign")
        return decision
    if ir["target_layer"] == "domain" and gate["verdict"] not in ("DENY", "HOLD"):
        decision.update(level=1, route="domain_bridge",
                        reason="domain layer: governed domain signal (bank/trading/gps)")
        return decision

    # --- Level 0: the frame decides, no token spent -------------------------
    if gate["verdict"] == "DENY":
        decision.update(route="denied", reason=gate["reason"])
        return decision
    if gate["verdict"] == "HOLD":
        decision.update(route="hold_commands_only", reason=gate["reason"])
        return decision
    # --- Level 1.5: local category solvers — deterministic, 0 token ----------
    # Only fires on unambiguous patterns (sentiment, simple math). The frame
    # (DENY/HOLD) has already been enforced above.
    solver_hit = try_local_solvers(raw)
    if solver_hit:
        decision.update(level=1, route="local_solver",
                        reason=f"category closed locally ({solver_hit['solver']}), no inference")
        decision["solver_answer"] = solver_hit["answer"]
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

    # --- Stack-layer routing (V3B) — governed surfaces, no remote tokens -----
    if ir["target_layer"] == "obsidure":
        decision.update(level=1, route="obsidure_route_only",
                        reason="obsidure layer: proposal-only routing, non-sovereign, no remote inference")
        return decision
    if ir["target_layer"] == "proof":
        decision.update(level=1, route="lean_route_only",
                        reason="proof/lean layer: formal surface check, no remote inference")
        return decision
    if ir["target_layer"] == "domain":
        decision.update(level=1, route="domain_bridge",
                        reason="domain layer: governed domain decision (bank/trading/gps), no LLM")
        return decision

    # --- Level 1: local proprietary organ -------------------------------------
    if ir["intent_type"] == "question" and not ir["needs"]["remote_model"]:
        decision.update(level=1, route="brody",
                        reason="semantic production on an already-structured request; local organ suffices")
        return decision

    # --- Level 3: justified remote escalation ---------------------------------
    # Single triage authority (LOT D): the model actually sent to
    # fireworks.chat() is decided here, once, from the resolved ladder.
    # No downstream caller (cli.py, run_official.py, run_benchmark.py) may
    # override this choice with a contract-preferred model.
    _answer_kind = "code_file" if ir["intent_type"] == "code_request" else None
    _selection = select_model_for_request(raw, ladder, answer_kind=_answer_kind)
    decision.update(level=3, route="fireworks", model=_selection["selected_model"],
                    reason=f"remote inference required; {_selection['selection_reason']}")
    # LOT E: expose the triage evidence itself (not just its outcome) so
    # metrics/receipts can audit "why", not only "which model".
    decision["selected_rung"] = _selection["selected_rung"]
    decision["selection_reason"] = _selection["selection_reason"]
    decision["ladder_size"] = len(ladder)
    decision["model_ladder"] = list(ladder)
    return decision
