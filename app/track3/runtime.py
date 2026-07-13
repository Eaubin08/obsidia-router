"""Track 3 Runtime — full escalation ladder with trace.

Pipeline (in order):
  LEVEL 0 — Natural input
              → UnifiedInputIR
              → ActivePlan
              → CapabilityResolver
              → Gates
              → HOLD / DENY / CLARIFY  [stops here]
              → ALLOW [continues]

  LEVEL 1 — Deterministic local solvers
              → T3 additive solvers (word_multiply, …)
              → Track 1 shared solvers (math, factual, sentiment, NER, code, …)
              → answer or abstention

  LEVEL 2 — Memory readonly
              → keyword lookup in memory_index.json
              → hit → answer;  miss → continue

  LEVEL 3 — Organ / model
              → Brody readonly (if BRODY_ENDPOINT loopback, single attempt)
              → Qwen local     (if llama-server loopback, single attempt)
              → UNRESOLVED if neither available or both fail

Invariants enforced:
  - decision_authority = KX108_ONLY
  - mutations_performed = []
  - external_calls = []
  - fireworks_attempted = False, tokens_remote = 0
  - At most one Brody call per run
  - At most one Qwen call per run
  - No subprocess, no git, no docker
  - Private layers (brody_real, obsidure, lean, sigma, oie) never executed
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
from app.track3 import brody_adapter
from app.track3 import memory_adapter
from app.track3.escalation_event import EscalationEvent
from app.track3.output_validator import validate_and_repair
from app.track3.t3_solvers import try_t3_solvers
from app.track3.v3b_surface import get_v3b_route_statuses, get_unavailable_v3b_routes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)


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


def _cap_info(cap_id: str, reason: str) -> dict:
    info = capability_resolver.get(cap_id)
    if info is None:
        info = {
            "capability_id":  cap_id,
            "description":    cap_id,
            "execution_class": "deterministic",
            "locality":       "local",
            "mutating":       False,
            "availability":   "available",
        }
    result = dict(info)
    result["reason_for_selection"] = reason
    return result


def _event(
    seq: int,
    level: str,
    stage: str,
    component: str,
    status: str,
    attempted: bool,
    selected: bool,
    available: bool,
    input_class: str,
    reason: str,
    t0: float,
    *,
    tokens_local: int = 0,
    evidence: dict | None = None,
) -> EscalationEvent:
    ts = _now_iso()
    return EscalationEvent(
        sequence=seq,
        level=level,
        stage=stage,
        component=component,
        status=status,
        attempted=attempted,
        selected=selected,
        available=available,
        input_class=input_class,
        reason=reason,
        started_at=ts,
        completed_at=ts,
        latency_ms=_ms(t0),
        tokens_local=tokens_local,
        tokens_remote=0,
        external_call=False,
        mutation=False,
        evidence=evidence or {},
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    raw: str,
    *,
    qwen_available: bool | None = None,
    brody_available: bool | None = None,
) -> dict:
    """Execute the Track 3 escalation ladder.

    Returns a fully populated ExecutionEnvelope dict.

    qwen_available:
        None  → auto-detected via qwen_local.is_available()
        True  → assume llama-server is up (for tests/mocks)
        False → skip Qwen

    brody_available:
        None  → auto-detected via brody_adapter.is_available()
        True  → assume Brody readonly endpoint is up (for tests/mocks)
        False → skip Brody readonly
    """
    run_start = datetime.now(timezone.utc)
    trace: list[dict] = []
    seq = 0
    latencies: dict[str, float | None] = {
        "ir_ms":             None,
        "plan_ms":           None,
        "gate_ms":           None,
        "t3_solvers_ms":     None,
        "local_solvers_ms":  None,
        "memory_ms":         None,
        "brody_readonly_ms": None,
        "qwen_ms":           None,
    }

    # Capability lists for envelope
    avail_caps  = list(capability_resolver.list_available().values())
    unavail_raw = capability_resolver.describe_unavailable()
    unavail_v3b = get_unavailable_v3b_routes()
    unavail_caps = unavail_raw + [
        {
            "capability_id": r["expected_route"],
            "status":        "route_only",
            "reason":        f"V3B bridge {r['bridge_type']} — not wired in T3 public deployment",
        }
        for r in unavail_v3b
    ]

    # ── LEVEL 0: IR → Plan → Gate ────────────────────────────────────────────

    t0 = time.perf_counter()
    ir = build_ir(raw)
    latencies["ir_ms"] = _ms(t0)

    t0 = time.perf_counter()
    plan = active_plan_mod.build(raw, ir)
    latencies["plan_ms"] = _ms(t0)

    t0 = time.perf_counter()
    gate_verdict = gates.evaluate(ir)
    latencies["gate_ms"] = _ms(t0)

    input_class = ir.get("intent_type", "unknown")
    caps_considered = avail_caps

    t0_gate = time.perf_counter()
    trace.append(_event(
        seq, "LEVEL_0", "gate_eval", "gates.evaluate",
        status="selected" if gate_verdict["verdict"] != "ALLOW" else "allow",
        attempted=True, selected=True, available=True,
        input_class=input_class,
        reason=f"gate={gate_verdict['verdict']}: {gate_verdict['reason']}",
        t0=t0_gate,
        evidence={"verdict": gate_verdict["verdict"], "matched": gate_verdict.get("matched")},
    ).to_dict())
    seq += 1

    verdict = gate_verdict["verdict"]

    # ── Gate intercept: HOLD / DENY / CLARIFY ────────────────────────────────

    if verdict == "DENY":
        completed = datetime.now(timezone.utc)
        ev = envelope_mod.build(
            request=raw, unified_ir=ir, active_plan=plan,
            capabilities_considered=caps_considered,
            capability_selected=_cap_info("deny", gate_verdict["reason"]),
            gate_verdict=gate_verdict,
            organ_invoked=None, model_invoked=None,
            answer=f"[DENY] {gate_verdict['reason']}",
            status="denied",
            unresolved_reason=None, external_calls=[],
            started_at=run_start, completed_at=completed,
            escalation_level_final="LEVEL_0",
            escalation_trace=trace,
            model_avoided=True,
            latency_by_stage=latencies,
            capabilities_available=avail_caps,
            capabilities_unavailable=unavail_caps,
        )
        ev["receipt_hash"] = receipt_mod.compute_hash(ev)
        return ev

    if verdict == "HOLD":
        completed = datetime.now(timezone.utc)
        ev = envelope_mod.build(
            request=raw, unified_ir=ir, active_plan=plan,
            capabilities_considered=caps_considered,
            capability_selected=_cap_info("hold", gate_verdict["reason"]),
            gate_verdict=gate_verdict,
            organ_invoked=None, model_invoked=None,
            answer=f"[HOLD] {gate_verdict['reason']} — no command auto-executed",
            status="held",
            unresolved_reason=None, external_calls=[],
            started_at=run_start, completed_at=completed,
            escalation_level_final="LEVEL_0",
            escalation_trace=trace,
            model_avoided=True,
            latency_by_stage=latencies,
            capabilities_available=avail_caps,
            capabilities_unavailable=unavail_caps,
        )
        ev["receipt_hash"] = receipt_mod.compute_hash(ev)
        return ev

    if verdict == "CLARIFY":
        completed = datetime.now(timezone.utc)
        ev = envelope_mod.build(
            request=raw, unified_ir=ir, active_plan=plan,
            capabilities_considered=caps_considered,
            capability_selected=_cap_info("clarify", gate_verdict["reason"]),
            gate_verdict=gate_verdict,
            organ_invoked=None, model_invoked=None,
            answer=_clarification_question(ir),
            status="clarification_required",
            unresolved_reason=None, external_calls=[],
            started_at=run_start, completed_at=completed,
            escalation_level_final="LEVEL_0",
            escalation_trace=trace,
            model_avoided=True,
            latency_by_stage=latencies,
            capabilities_available=avail_caps,
            capabilities_unavailable=unavail_caps,
        )
        ev["receipt_hash"] = receipt_mod.compute_hash(ev)
        return ev

    # ── LEVEL 1: Deterministic solvers ───────────────────────────────────────

    # T3 additive solvers first
    t0 = time.perf_counter()
    t3_result = try_t3_solvers(raw)
    latencies["t3_solvers_ms"] = _ms(t0)

    if t3_result is not None:
        actual_cap_id = _solver_to_cap_id(t3_result["solver"])
        trace.append(_event(
            seq, "LEVEL_1", "t3_solver", t3_result["solver"],
            status="selected", attempted=True, selected=True, available=True,
            input_class=input_class,
            reason=f"T3 solver matched: {t3_result['solver']}",
            t0=t0,
            evidence={"solver": t3_result["solver"], "answer": t3_result["answer"]},
        ).to_dict())
        seq += 1
        completed = datetime.now(timezone.utc)
        ev = envelope_mod.build(
            request=raw, unified_ir=ir, active_plan=plan,
            capabilities_considered=caps_considered,
            capability_selected=_cap_info(
                actual_cap_id, f"local solver matched: {t3_result['solver']}"
            ),
            gate_verdict=gate_verdict,
            organ_invoked=t3_result["solver"], model_invoked=None,
            answer=t3_result["answer"],
            status="resolved",
            unresolved_reason=None, external_calls=[],
            started_at=run_start, completed_at=completed,
            escalation_level_final="LEVEL_1",
            escalation_trace=trace,
            model_avoided=True,
            local_solver_attempted=True,
            local_solver_selected=t3_result["solver"],
            latency_by_stage=latencies,
            capabilities_available=avail_caps,
            capabilities_unavailable=unavail_caps,
        )
        ev["receipt_hash"] = receipt_mod.compute_hash(ev)
        return ev

    # Track 1 shared solvers
    t0 = time.perf_counter()
    local_result = try_local_solvers(raw)
    latencies["local_solvers_ms"] = _ms(t0)

    if local_result is not None:
        actual_cap_id = _solver_to_cap_id(local_result["solver"])
        trace.append(_event(
            seq, "LEVEL_1", "local_solver", local_result["solver"],
            status="selected", attempted=True, selected=True, available=True,
            input_class=input_class,
            reason=f"Track 1 local solver matched: {local_result['solver']}",
            t0=t0,
            evidence={"solver": local_result["solver"], "answer": local_result["answer"]},
        ).to_dict())
        seq += 1
        completed = datetime.now(timezone.utc)
        ev = envelope_mod.build(
            request=raw, unified_ir=ir, active_plan=plan,
            capabilities_considered=caps_considered,
            capability_selected=_cap_info(
                actual_cap_id, f"local solver matched: {local_result['solver']}"
            ),
            gate_verdict=gate_verdict,
            organ_invoked=local_result["solver"], model_invoked=None,
            answer=local_result["answer"],
            status="resolved",
            unresolved_reason=None, external_calls=[],
            started_at=run_start, completed_at=completed,
            escalation_level_final="LEVEL_1",
            escalation_trace=trace,
            model_avoided=True,
            local_solver_attempted=True,
            local_solver_selected=local_result["solver"],
            latency_by_stage=latencies,
            capabilities_available=avail_caps,
            capabilities_unavailable=unavail_caps,
        )
        ev["receipt_hash"] = receipt_mod.compute_hash(ev)
        return ev

    # LEVEL_1 abstention
    trace.append(_event(
        seq, "LEVEL_1", "local_solver", "local_solvers",
        status="abstained", attempted=True, selected=False, available=True,
        input_class=input_class,
        reason="no deterministic solver pattern matched",
        t0=t0,
    ).to_dict())
    seq += 1

    # ── LEVEL 2: Memory readonly ──────────────────────────────────────────────

    t0 = time.perf_counter()
    mem_result = memory_adapter.lookup(raw, ir)
    latencies["memory_ms"] = _ms(t0)

    if mem_result is not None:
        trace.append(_event(
            seq, "LEVEL_2", "memory_lookup", "memory_index",
            status="selected", attempted=True, selected=True, available=True,
            input_class=input_class,
            reason=f"memory key matched: {mem_result['source_key']} "
                   f"({mem_result['match_count']} keywords)",
            t0=t0,
            evidence={"source_key": mem_result["source_key"],
                      "match_count": mem_result["match_count"]},
        ).to_dict())
        seq += 1
        completed = datetime.now(timezone.utc)
        ev = envelope_mod.build(
            request=raw, unified_ir=ir, active_plan=plan,
            capabilities_considered=caps_considered,
            capability_selected=_cap_info(
                "memory_lookup",
                f"memory key matched: {mem_result['source_key']}",
            ),
            gate_verdict=gate_verdict,
            organ_invoked="memory_index", model_invoked=None,
            answer=mem_result["answer"],
            status="resolved",
            unresolved_reason=None, external_calls=[],
            started_at=run_start, completed_at=completed,
            escalation_level_final="LEVEL_2",
            escalation_trace=trace,
            model_avoided=True,
            local_solver_attempted=True,
            memory_attempted=True,
            memory_hit=True,
            memory_source=mem_result["source_key"],
            latency_by_stage=latencies,
            capabilities_available=avail_caps,
            capabilities_unavailable=unavail_caps,
        )
        ev["receipt_hash"] = receipt_mod.compute_hash(ev)
        return ev

    # LEVEL_2 miss
    trace.append(_event(
        seq, "LEVEL_2", "memory_lookup", "memory_index",
        status="abstained", attempted=True, selected=False, available=True,
        input_class=input_class,
        reason="no memory entry keyword threshold reached",
        t0=t0,
    ).to_dict())
    seq += 1

    # ── LEVEL 3: Brody readonly ───────────────────────────────────────────────

    brody_t3_available: bool
    if brody_available is None:
        brody_t3_available = brody_adapter.is_available()
    else:
        brody_t3_available = bool(brody_available)

    brody_latency: float | None = None
    brody_was_attempted = False

    if brody_t3_available:
        brody_was_attempted = True
        t0 = time.perf_counter()
        brody_result = brody_adapter.chat(raw)
        brody_latency = _ms(t0)
        latencies["brody_readonly_ms"] = brody_latency

        if brody_result.get("success"):
            text = brody_result["text"]
            validation = validate_and_repair(text, "brody_readonly")
            if validation["valid"]:
                trace.append(_event(
                    seq, "LEVEL_3", "brody_readonly", "brody_readonly_adapter",
                    status="selected", attempted=True, selected=True, available=True,
                    input_class=input_class,
                    reason="brody readonly live call succeeded",
                    t0=t0,
                    evidence={"brody_mode": brody_result.get("brody_mode"),
                               "governance_ok": brody_result.get("governance_ok")},
                ).to_dict())
                seq += 1
                completed = datetime.now(timezone.utc)
                ev = envelope_mod.build(
                    request=raw, unified_ir=ir, active_plan=plan,
                    capabilities_considered=caps_considered,
                    capability_selected=_cap_info(
                        "brody_readonly",
                        "brody readonly endpoint available and responded",
                    ),
                    gate_verdict=gate_verdict,
                    organ_invoked="brody_readonly",
                    model_invoked="brody_readonly/live",
                    answer=validation["answer"],
                    status="resolved",
                    unresolved_reason=None, external_calls=[],
                    started_at=run_start, completed_at=completed,
                    escalation_level_final="LEVEL_3",
                    escalation_trace=trace,
                    model_avoided=False,
                    local_solver_attempted=True,
                    memory_attempted=True,
                    organ_considered=["brody_readonly"],
                    brody_readonly_attempted=True,
                    brody_readonly_available=True,
                    tokens_local=0,
                    latency_by_stage=latencies,
                    capabilities_available=avail_caps,
                    capabilities_unavailable=unavail_caps,
                )
                ev["receipt_hash"] = receipt_mod.compute_hash(ev)
                return ev

        # Brody call failed or returned invalid output
        trace.append(_event(
            seq, "LEVEL_3", "brody_readonly", "brody_readonly_adapter",
            status="invalid_output" if brody_result.get("success") else "failed",
            attempted=True, selected=False, available=True,
            input_class=input_class,
            reason=brody_result.get("error") or "brody response invalid after repair",
            t0=t0,
            evidence={"brody_mode": brody_result.get("brody_mode", "unknown")},
        ).to_dict())
        seq += 1
    else:
        latencies["brody_readonly_ms"] = None
        trace.append(_event(
            seq, "LEVEL_3", "brody_readonly", "brody_readonly_adapter",
            status="unavailable", attempted=False, selected=False, available=False,
            input_class=input_class,
            reason="BRODY_ENDPOINT not set or health check failed",
            t0=time.perf_counter(),
        ).to_dict())
        seq += 1

    # ── LEVEL 3: Qwen local ───────────────────────────────────────────────────

    if qwen_available is None:
        from app.adapters.qwen_local import is_available as _qwen_is_available
        qwen_available = _qwen_is_available()

    qwen_was_attempted = False
    qwen_latency: float | None = None

    if qwen_available:
        qwen_was_attempted = True
        from app.adapters.qwen_local import chat as qwen_chat

        t0 = time.perf_counter()
        qr = qwen_chat(raw)
        qwen_latency = _ms(t0)
        latencies["qwen_ms"] = qwen_latency

        if qr["success"]:
            validation = validate_and_repair(qr["text"], "local_qwen")
            if validation["valid"]:
                trace.append(_event(
                    seq, "LEVEL_3", "qwen_local", "qwen_local_adapter",
                    status="selected", attempted=True, selected=True, available=True,
                    input_class=input_class,
                    reason="Qwen local call succeeded and output is valid",
                    t0=t0,
                    tokens_local=qr.get("local_model_tokens") or 0,
                    evidence={"repaired": validation["repaired"],
                               "provider": qr.get("provider", "qwen_local")},
                ).to_dict())
                seq += 1
                completed = datetime.now(timezone.utc)
                model_id = "qwen_local/qwen2.5-3b-instruct-q4_k_m"
                ev = envelope_mod.build(
                    request=raw, unified_ir=ir, active_plan=plan,
                    capabilities_considered=caps_considered,
                    capability_selected=_cap_info(
                        "local_qwen",
                        "no deterministic solver matched; local model invoked",
                    ),
                    gate_verdict=gate_verdict,
                    organ_invoked=None, model_invoked=model_id,
                    answer=validation["answer"],
                    status="resolved",
                    unresolved_reason=None, external_calls=[],
                    started_at=run_start, completed_at=completed,
                    escalation_level_final="LEVEL_3",
                    escalation_trace=trace,
                    model_avoided=False,
                    local_solver_attempted=True,
                    memory_attempted=True,
                    organ_considered=["brody_readonly", "local_qwen"],
                    brody_readonly_attempted=brody_was_attempted,
                    brody_readonly_available=brody_t3_available,
                    qwen_attempted=True,
                    tokens_local=qr.get("local_model_tokens") or 0,
                    latency_by_stage=latencies,
                    capabilities_available=avail_caps,
                    capabilities_unavailable=unavail_caps,
                )
                ev["receipt_hash"] = receipt_mod.compute_hash(ev)
                return ev

            # Qwen output invalid even after repair
            trace.append(_event(
                seq, "LEVEL_3", "qwen_local", "qwen_local_adapter",
                status="invalid_output", attempted=True, selected=False, available=True,
                input_class=input_class,
                reason=f"output validation failed: {validation['reason']}",
                t0=t0,
            ).to_dict())
            seq += 1
            error_msg = f"qwen output invalid: {validation['reason']}"
        else:
            latencies["qwen_ms"] = qwen_latency
            trace.append(_event(
                seq, "LEVEL_3", "qwen_local", "qwen_local_adapter",
                status="failed", attempted=True, selected=False, available=True,
                input_class=input_class,
                reason=qr.get("error") or "qwen call failed",
                t0=t0,
            ).to_dict())
            seq += 1
            error_msg = qr.get("error", "qwen_local call failed")
    else:
        latencies["qwen_ms"] = None
        trace.append(_event(
            seq, "LEVEL_3", "qwen_local", "qwen_local_adapter",
            status="unavailable", attempted=False, selected=False, available=False,
            input_class=input_class,
            reason="llama-server not running on loopback; Fireworks disabled in Track 3",
            t0=time.perf_counter(),
        ).to_dict())
        seq += 1
        error_msg = (
            "no_local_model_available — "
            "llama-server not running on loopback; "
            "Fireworks disabled in Track 3 runtime; "
            "request is open and cannot be closed locally"
        )

    # ── Unresolved ────────────────────────────────────────────────────────────

    completed = datetime.now(timezone.utc)
    ev = envelope_mod.build(
        request=raw, unified_ir=ir, active_plan=plan,
        capabilities_considered=caps_considered,
        capability_selected=_cap_info(
            "local_qwen",
            "escalation exhausted — no capability resolved the request",
        ),
        gate_verdict=gate_verdict,
        organ_invoked=None,
        model_invoked="qwen_local/qwen2.5-3b-instruct-q4_k_m" if qwen_was_attempted else None,
        answer="",
        status="unresolved",
        unresolved_reason=error_msg,
        external_calls=[],
        started_at=run_start, completed_at=completed,
        escalation_level_final="UNRESOLVED",
        escalation_trace=trace,
        model_avoided=not (brody_was_attempted or qwen_was_attempted),
        local_solver_attempted=True,
        memory_attempted=True,
        organ_considered=["brody_readonly", "local_qwen"],
        brody_readonly_attempted=brody_was_attempted,
        brody_readonly_available=brody_t3_available,
        qwen_attempted=qwen_was_attempted,
        latency_by_stage=latencies,
        capabilities_available=avail_caps,
        capabilities_unavailable=unavail_caps,
    )
    ev["receipt_hash"] = receipt_mod.compute_hash(ev)
    return ev
