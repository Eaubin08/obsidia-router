"""ExecutionEnvelope — canonical result wrapper for Track 3 runtime.

schema_version: track3/2.0 (adds escalation trace and level fields)
decision_authority: KX108_ONLY (hardcoded — never overridden by caller)
mutations_performed: always [] (Track 3 is read-only)
fireworks_attempted: always False (Fireworks disabled in Track 3)
tokens_remote: always 0 (zero remote tokens)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def build(
    *,
    request: str,
    unified_ir: dict,
    active_plan: dict,
    capabilities_considered: list[dict],
    capability_selected: dict,
    gate_verdict: dict,
    organ_invoked: str | None,
    model_invoked: str | None,
    answer: str,
    status: str,
    unresolved_reason: str | None,
    external_calls: list,
    started_at: datetime,
    completed_at: datetime,
    # ── Escalation trace (new in track3/2.0) ────────────────────────────────
    escalation_level_final: str = "UNRESOLVED",
    escalation_trace: list | None = None,
    # ── Detailed execution flags ─────────────────────────────────────────────
    model_avoided: bool = False,
    local_solver_attempted: bool = False,
    local_solver_selected: str | None = None,
    memory_attempted: bool = False,
    memory_hit: bool = False,
    memory_source: str | None = None,
    organ_considered: list | None = None,
    brody_readonly_attempted: bool = False,
    brody_readonly_available: bool = False,
    qwen_attempted: bool = False,
    fireworks_attempted: bool = False,
    tokens_local: int = 0,
    tokens_remote: int = 0,
    latency_by_stage: dict | None = None,
    capabilities_available: list | None = None,
    capabilities_unavailable: list | None = None,
) -> dict:
    """Build a Track 3 ExecutionEnvelope.

    receipt_hash is set to an empty string here; the caller (runtime.py) must
    overwrite it with the canonical SHA-256 after the envelope is complete.

    All new keyword arguments have safe defaults so that callers that don't
    pass them (including test helpers) continue to work without modification.
    """
    duration_ms = round(
        (completed_at - started_at).total_seconds() * 1000, 2
    )
    return {
        # ── Core identity ────────────────────────────────────────────────────
        "schema_version":          "track3/2.0",
        "run_id":                  str(uuid.uuid4()),
        "request":                 request,
        # ── Governed pipeline ────────────────────────────────────────────────
        "unified_ir":              unified_ir,
        "active_plan":             active_plan,
        "capabilities_considered": capabilities_considered,
        "capabilities_available":  list(capabilities_available or []),
        "capabilities_unavailable": list(capabilities_unavailable or []),
        "capability_selected":     capability_selected,
        "gate_verdict":            gate_verdict,
        # ── Escalation trace ─────────────────────────────────────────────────
        "escalation_level_final":  escalation_level_final,
        "escalation_trace":        list(escalation_trace or []),
        # ── Execution detail ─────────────────────────────────────────────────
        "local_solver_attempted":  local_solver_attempted,
        "local_solver_selected":   local_solver_selected,
        "memory_attempted":        memory_attempted,
        "memory_hit":              memory_hit,
        "memory_source":           memory_source,
        "organ_considered":        list(organ_considered or []),
        "organ_invoked":           organ_invoked,
        "brody_readonly_attempted": brody_readonly_attempted,
        "brody_readonly_available": brody_readonly_available,
        "qwen_attempted":          qwen_attempted,
        "fireworks_attempted":     False,   # immutable invariant
        "model_invoked":           model_invoked,
        "model_avoided":           model_avoided,
        # ── Token accounting ─────────────────────────────────────────────────
        "tokens_local":            tokens_local,
        "tokens_remote":           0,       # immutable invariant
        # ── Latency ──────────────────────────────────────────────────────────
        "latency_by_stage":        dict(latency_by_stage or {}),
        # ── Result ───────────────────────────────────────────────────────────
        "decision_authority":      "KX108_ONLY",
        "answer":                  answer,
        "status":                  status,
        "unresolved_reason":       unresolved_reason,
        "mutations_performed":     [],
        "external_calls":          list(external_calls),
        # ── Timing ───────────────────────────────────────────────────────────
        "started_at":              started_at.isoformat(),
        "completed_at":            completed_at.isoformat(),
        "duration_ms":             duration_ms,
        # ── Integrity ────────────────────────────────────────────────────────
        "receipt_hash":            "",
    }
