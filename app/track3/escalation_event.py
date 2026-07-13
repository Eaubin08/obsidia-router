"""EscalationEvent — one entry in the escalation trace for a Track 3 run.

Each run produces a list of EscalationEvents, one per stage attempted.
The list is ordered by sequence (0, 1, 2, …) and never modified after the
run completes.

Invariants:
  - external_call = False always (Track 3 is loopback-only)
  - mutation = False always (Track 3 is read-only)
  - tokens_remote = 0 always (Fireworks disabled)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EscalationEvent:
    sequence: int
    level: str       # LEVEL_0 | LEVEL_1 | LEVEL_2 | LEVEL_3
    stage: str       # ir_build | plan_build | gate_eval | t3_solver |
                     # local_solver | memory_lookup | brody_readonly | qwen_local
    component: str   # human-readable component name
    status: str      # attempted | selected | skipped | abstained | unavailable |
                     # failed | invalid_output
    attempted: bool
    selected: bool
    available: bool
    input_class: str          # intent_type from IR
    reason: str               # why this event fired / was skipped
    started_at: str           # ISO 8601 UTC
    completed_at: str         # ISO 8601 UTC
    latency_ms: float
    tokens_local: int = 0
    tokens_remote: int = 0    # always 0
    external_call: bool = False  # always False
    mutation: bool = False       # always False
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sequence":     self.sequence,
            "level":        self.level,
            "stage":        self.stage,
            "component":    self.component,
            "status":       self.status,
            "attempted":    self.attempted,
            "selected":     self.selected,
            "available":    self.available,
            "input_class":  self.input_class,
            "reason":       self.reason,
            "started_at":   self.started_at,
            "completed_at": self.completed_at,
            "latency_ms":   self.latency_ms,
            "tokens_local": self.tokens_local,
            "tokens_remote": self.tokens_remote,
            "external_call": self.external_call,
            "mutation":     self.mutation,
            "evidence":     self.evidence,
        }
