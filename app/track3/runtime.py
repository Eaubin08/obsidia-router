"""Track 3 Runtime — orchestrates the full pipeline.

Pipeline:
  raw input
  → UnifiedInputIR
  → ActivePlan
  → CapabilityResolver.select()
  → Gates.evaluate()
  → _execute() → CapabilityExecutionResult
  → OutputValidator (model paths only)
  → ExecutionEnvelope
  → receipt_hash (SHA-256)

Invariants enforced here:
  - decision_authority = KX108_ONLY (hardcoded)
  - mutations_performed = [] always
  - external_calls = [] for all local and loopback paths
  - Fireworks adapter never imported or called
  - No subprocess, no git ops, no docker ops
  - Qwen on loopback only (qwen_local enforces this internally)
  - Unavailable capabilities (brody, lean, obsidure, sigma, oie) never executed
  - Exactly one capability selected per run
  - At most one model invocation per run (no retry loop)
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from app.ir.unified_ir import build_ir
from app.gates import gates
from app.router.local_solvers import try_local_solvers
from app.track3 import active_plan as active_plan_mod
from app.track3 import capability_resolver
from app.track3 import envelope as envelope_mod
from app.track3 import receipt as receipt_mod
from app.track3.capability_result import CapabilityExecutionResult
from app.track3.t3_solvers import try_t3_solvers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clarification_question(ir: dict) -> str:
    missing = ir.get("missing", [])
    if "intent" in missing:
        return (
            "Your request intent is unclear. "
            "Could you specify what you want to achieve? "
            "(e.g., answer a question, write code, plan something, check a fact)"
        )
    if "target_scope" in missing:
        return "What is the target scope or file for this code request?"
    if "target_layer" in missing:
        return "Which layer or system are you targeting with this request?"
    return (
        "Additional information is needed. "
        "Could you provide more details about your request?"
    )


def _solver_to_cap_id(solver: str) -> str:
    if "math" in solver or "rate" in solver or "multiply" in solver:
        return "deterministic_math"
    if "sentiment" in solver:
        return "deterministic_sentiment"
    if "ner" in solver:
        return "deterministic_ner"
    if "fact" in solver:
        return "deterministic_factual"
    if "code" in solver or "cache" in solver or "cap" in solver:
        return "deterministic_code"
    if "summary" in solver or "logic" in solver or "brody" in solver:
        return "deterministic_factual"
    return "structural_answer"


# ---------------------------------------------------------------------------
# Capability execution (returns CapabilityExecutionResult)
# ---------------------------------------------------------------------------

def _execute(
    cap_id: str,
    raw: str,
    ir: dict,
    gate_verdict: dict,
    qwen_available: bool | None,
) -> CapabilityExecutionResult:
    """Execute a single capability. Returns CapabilityExecutionResult.

    - Never returns the ExecutionEnvelope (runtime builds it).
    - Never calls Fireworks.
    - At most one model call (no retry).
    - No subprocess, no git, no docker.
    """
    t0 = time.perf_counter()

    def _elapsed() -> float:
        return round((time.perf_counter() - t0) * 1000, 2)

    # ── Gate-intercepted paths ────────────────────────────────────────────────
    if cap_id == "deny":
        return CapabilityExecutionResult(
            capability_id="deny",
            status="denied",
            answer=f"[DENY] {gate_verdict['reason']}",
            local_execution=True,
            elapsed_ms=_elapsed(),
        )

    if cap_id == "hold":
        return CapabilityExecutionResult(
            capability_id="hold",
            status="held",
            answer=f"[HOLD] {gate_verdict['reason']} — no command auto-executed",
            local_execution=True,
            elapsed_ms=_elapsed(),
        )

    if cap_id == "clarify":
        return CapabilityExecutionResult(
            capability_id="clarify",
            status="clarification_required",
            answer=_clarification_question(ir),
            local_execution=True,
            elapsed_ms=_elapsed(),
        )

    # ── ALLOW path: deterministic solvers first ───────────────────────────────

    # Track 3 specific solvers (additive, do not modify Track 1)
    t3_result = try_t3_solvers(raw)
    if t3_result is not None:
        actual_cap = _solver_to_cap_id(t3_result["solver"])
        return CapabilityExecutionResult(
            capability_id=actual_cap,
            status="resolved",
            answer=t3_result["answer"],
            organ_invoked=t3_result["solver"],
            local_execution=True,
            elapsed_ms=_elapsed(),
            evidence={"solver": t3_result["solver"]},
        )

    # Track 1 shared solvers
    local_result = try_local_solvers(raw)
    if local_result is not None:
        actual_cap = _solver_to_cap_id(local_result["solver"])
        return CapabilityExecutionResult(
            capability_id=actual_cap,
            status="resolved",
            answer=local_result["answer"],
            organ_invoked=local_result["solver"],
            local_execution=True,
            elapsed_ms=_elapsed(),
            evidence={"solver": local_result["solver"]},
        )

    # ── Local Qwen (single attempt, no retry) ─────────────────────────────────
    if qwen_available is None:
        from app.adapters.qwen_local import is_available
        qwen_available = is_available()

    if qwen_available:
        from app.adapters.qwen_local import chat as qwen_chat
        from app.track3.output_validator import validate_and_repair

        qr = qwen_chat(raw)
        elapsed = _elapsed()

        if qr["success"]:
            validation = validate_and_repair(qr["text"], "local_qwen")
            if validation["valid"]:
                return CapabilityExecutionResult(
                    capability_id="local_qwen",
                    status="resolved",
                    answer=validation["answer"],
                    model_invoked="qwen_local/qwen2.5-3b-instruct-q4_k_m",
                    local_execution=True,
                    elapsed_ms=elapsed,
                    evidence={
                        "local_model_tokens": qr.get("local_model_tokens"),
                        "repaired":           validation["repaired"],
                        "provider":           qr.get("provider", "qwen_local"),
                    },
                )
            # Output invalid even after repair
            return CapabilityExecutionResult(
                capability_id="local_qwen",
                status="unresolved",
                answer="",
                model_invoked="qwen_local/qwen2.5-3b-instruct-q4_k_m",
                local_execution=True,
                elapsed_ms=elapsed,
                error_code="invalid_output",
                error_message=f"output validation failed: {validation['reason']}",
                evidence={"local_model_tokens": qr.get("local_model_tokens")},
            )

        # qwen_chat itself failed
        return CapabilityExecutionResult(
            capability_id="local_qwen",
            status="unresolved",
            answer="",
            model_invoked="qwen_local/qwen2.5-3b-instruct-q4_k_m",
            local_execution=True,
            elapsed_ms=_elapsed(),
            error_code=qr.get("status", "error"),
            error_message=qr.get("error", "qwen_local call failed"),
        )

    # ── No model available ────────────────────────────────────────────────────
    return CapabilityExecutionResult(
        capability_id="local_qwen",
        status="unresolved",
        answer="",
        local_execution=True,
        elapsed_ms=_elapsed(),
        error_code="unavailable",
        error_message=(
            "no_local_model_available — "
            "llama-server not running on loopback; "
            "Fireworks disabled in Track 3 runtime; "
            "request is open and cannot be closed locally"
        ),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(raw: str, *, qwen_available: bool | None = None) -> dict:
    """Execute Track 3 pipeline. Returns a fully populated ExecutionEnvelope dict.

    qwen_available:
        None  → auto-detected via qwen_local.is_available()
        True  → assume llama-server is up (skip health check — for tests/mocks)
        False → skip Qwen; unresolved open questions stay unresolved
    """
    started_at = datetime.now(timezone.utc)

    # ── Steps 1-2: IR + Plan ─────────────────────────────────────────────────
    ir   = build_ir(raw)
    plan = active_plan_mod.build(raw, ir)

    # ── Step 3: Gate evaluation ──────────────────────────────────────────────
    gate_verdict = gates.evaluate(ir)

    # ── Step 4: Capability selection ─────────────────────────────────────────
    initial_cap_id, initial_cap_info = capability_resolver.select(plan, gate_verdict)
    caps_considered = list(capability_resolver.list_available().values())

    # ── Step 5: Execute → CapabilityExecutionResult ──────────────────────────
    result = _execute(initial_cap_id, raw, ir, gate_verdict, qwen_available)

    completed_at = datetime.now(timezone.utc)

    # ── Step 6: Resolve final capability info ─────────────────────────────────
    # The executed capability may differ from the initially selected one
    # (e.g. a T3 solver fired before local_qwen was tried).
    actual_cap_info = capability_resolver.get(result.capability_id)
    if actual_cap_info is None:
        actual_cap_info = initial_cap_info
    actual_cap_info = dict(actual_cap_info)

    # Update selection reason to reflect what actually ran
    if result.organ_invoked:
        actual_cap_info["reason_for_selection"] = (
            f"local solver matched: {result.organ_invoked}"
        )
    elif result.model_invoked:
        actual_cap_info["reason_for_selection"] = (
            "no deterministic solver matched; local model invoked"
        )

    # ── Step 7: Build ExecutionEnvelope ──────────────────────────────────────
    unresolved_reason = result.error_message if result.status == "unresolved" else None

    ev = envelope_mod.build(
        request=raw,
        unified_ir=ir,
        active_plan=plan,
        capabilities_considered=caps_considered,
        capability_selected=actual_cap_info,
        gate_verdict=gate_verdict,
        organ_invoked=result.organ_invoked,
        model_invoked=result.model_invoked,
        answer=result.answer,
        status=result.status,
        unresolved_reason=unresolved_reason,
        external_calls=result.external_calls,
        started_at=started_at,
        completed_at=completed_at,
    )

    # ── Step 8: Receipt hash ─────────────────────────────────────────────────
    ev["receipt_hash"] = receipt_mod.compute_hash(ev)

    return ev
