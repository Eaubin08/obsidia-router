"""CapabilityExecutionResult — contract for every Track 3 capability execution.

Rules:
- No capability returns the ExecutionEnvelope directly (runtime builds it).
- external_calls must be [] for all local paths (loopback is not external).
- mutations_performed must always be [].
- error_message must never contain secrets or private user paths.
- No chain_of_thought, reasoning, or hidden_state fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CapabilityExecutionResult:
    capability_id: str
    status: str           # resolved | unresolved | unavailable | held | denied | clarification_required
    answer: str
    organ_invoked: str | None = None
    model_invoked: str | None = None
    local_execution: bool = True
    external_calls: list = field(default_factory=list)
    mutations_performed: list = field(default_factory=list)
    elapsed_ms: float = 0.0
    error_code: str | None = None
    error_message: str | None = None
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "capability_id":      self.capability_id,
            "status":             self.status,
            "answer":             self.answer,
            "organ_invoked":      self.organ_invoked,
            "model_invoked":      self.model_invoked,
            "local_execution":    self.local_execution,
            "external_calls":     list(self.external_calls),
            "mutations_performed": list(self.mutations_performed),
            "elapsed_ms":         round(self.elapsed_ms, 2),
            "error_code":         self.error_code,
            "error_message":      self.error_message,
            "evidence":           dict(self.evidence),
        }
