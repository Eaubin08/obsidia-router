"""Model triage — single authority for "which model" (LOT D).

ALLOWED_MODELS parsing is owned by app.adapters.fireworks.allowed_models()
(LOT C). This module owns the next, separate decision: once a Fireworks
escalation is already justified by the router, which rung of the resolved
ladder is sufficient.

Duplicates a small code-signal table also used (in a richer form) by
benchmarks/track1_remote_answer_contract.py. Kept local rather than
imported, because app/ never imports from benchmarks/ (benchmarks/ depends
on app/, not the reverse) and this module must stay usable from app/cli.py
and app/router/decision.py without a layering violation.
"""
from __future__ import annotations

RUNG_SMALL = 0
RUNG_MEDIUM = 1
RUNG_LARGE = 2

_CODE_SIGNALS: frozenset[str] = frozenset({
    "implement", "implémente", "implemente", "function", "fonction",
    "def ", "class ", "script", "programme", "program", ".py",
    "unittest", "pytest", "debug", "bug", "fix",
})

_COMPLEX_CODE_SIGNALS: frozenset[str] = frozenset({
    "complex", "complexe", "multi-file", "multithread", "concurrency",
    "concurrent", "distributed", "async", "refactor", "architecture",
})

_LONG_PROMPT_CHARS = 400


def select_rung(request: str, answer_kind: str | None = None) -> int:
    """Deterministic rung in [RUNG_SMALL, RUNG_LARGE]. Request signals only
    — never task_id.

    RUNG_SMALL  — short/medium non-code request (<= 400 chars).
    RUNG_MEDIUM — long non-code request (> 400 chars), or a code request
                  with no complexity signal.
    RUNG_LARGE  — code request flagged complex (explicit signal or long).
    """
    # LOT H1: summarisation is a compact transformation task.
    # Keep it on rung 0; complexity must not promote it to a model
    # known to emit long planning content before the requested summary.
    if answer_kind == "structured_summary":
        return 0
    low = request.lower()
    is_code = (answer_kind == "code_file") or any(s in low for s in _CODE_SIGNALS)
    is_long = len(request) > _LONG_PROMPT_CHARS
    if is_code and (is_long or any(s in low for s in _COMPLEX_CODE_SIGNALS)):
        return RUNG_LARGE
    if is_code:
        return RUNG_MEDIUM
    if is_long:
        return RUNG_MEDIUM
    return RUNG_SMALL


def select_model_for_request(
    request: str,
    allowed_models: list[str],
    answer_kind: str | None = None,
) -> dict:
    """Single authority for the model actually sent to fireworks.chat().

    allowed_models must be the fully resolved, ordered ladder (index 0 is
    the harness's stated first-choice/cheapest model). Order is the
    caller's authority — this function never reorders or reinterprets it
    by model name; it only picks an index.

    A ladder shorter than the computed rung degrades gracefully to its
    last available index; a 1-model ladder always resolves to that model.

    Returns {"selected_model", "selected_rung", "selection_reason"}.
    """
    if not allowed_models:
        raise ValueError("select_model_for_request requires a non-empty ladder")
    rung = select_rung(request, answer_kind)
    clamped = min(rung, len(allowed_models) - 1)
    reason = f"rung {rung} of {len(allowed_models)}-model ladder"
    if clamped != rung:
        reason += f" (clamped to {clamped}: ladder shorter than computed rung)"
    return {
        "selected_model": allowed_models[clamped],
        "selected_rung": clamped,
        "selection_reason": reason,
    }
