"""ExecutionEnvelope — canonical result wrapper for Track 3 runtime.

schema_version: track3/1.0
decision_authority: KX108_ONLY (hardcoded — never overridden by caller)
mutations_performed: always [] (Track 3 is read-only)
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
) -> dict:
    """Build a Track 3 ExecutionEnvelope.

    receipt_hash is set to an empty string here; the caller (runtime.py) must
    overwrite it with the canonical SHA-256 after the envelope is complete.
    """
    duration_ms = round(
        (completed_at - started_at).total_seconds() * 1000, 2
    )
    return {
        "schema_version":         "track3/1.0",
        "run_id":                 str(uuid.uuid4()),
        "request":                request,
        "unified_ir":             unified_ir,
        "active_plan":            active_plan,
        "capabilities_considered": capabilities_considered,
        "capability_selected":    capability_selected,
        "gate_verdict":           gate_verdict,
        "organ_invoked":          organ_invoked,
        "model_invoked":          model_invoked,
        "decision_authority":     "KX108_ONLY",
        "answer":                 answer,
        "status":                 status,
        "unresolved_reason":      unresolved_reason,
        "mutations_performed":    [],
        "external_calls":         list(external_calls),
        "started_at":             started_at.isoformat(),
        "completed_at":           completed_at.isoformat(),
        "duration_ms":            duration_ms,
        "receipt_hash":           "",
    }
