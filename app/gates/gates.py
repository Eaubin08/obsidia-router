"""Gates — deterministic guard layer between the IR and any inference.

Adapted from the Obsidia X-108 policy_check (word-boundary matching to avoid
false positives such as 'act' inside 'actuelle', 'action', 'transaction').

Verdicts, strongest first: DENY > HOLD > CLARIFY > ALLOW.
The gates can stop a request before a single token is spent.
"""
from __future__ import annotations

import re

# Requests containing these are refused outright (destructive / out of frame).
DENY_KEYWORDS = [
    "force-push", "force push", "rm -rf", "drop database", "format c",
    "disable gates", "bypass gates", "skip invariants",
]

# Requests containing these are held: the router answers with a bounded
# HOLD / commands-only output and never auto-executes. Invariants:
# no_auto_act, no_auto_commit, no_auto_push.
HOLD_KEYWORDS = [
    "push", "commit", "deploy", "deploie", "delete", "supprime",
    "execute", "run", "lance", "install", "installe", "act", "autorise",
]


def _key_match(key: str, normalized: str) -> bool:
    """Word-boundary match. 'act' must not match 'actuelle' or 'impact'."""
    if " " in key:
        return key in normalized
    return re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", normalized) is not None


def evaluate(ir: dict) -> dict:
    """Evaluate the gates on a built IR. Deterministic, no inference."""
    normalized = ir["normalized"]

    for kw in DENY_KEYWORDS:
        if _key_match(kw, normalized):
            return {
                "verdict": "DENY",
                "matched": kw,
                "invariants": ["no_auto_act"],
                "reason": f"deny keyword '{kw}' — out of authorized frame",
            }

    for kw in HOLD_KEYWORDS:
        if _key_match(kw, normalized):
            return {
                "verdict": "HOLD",
                "matched": kw,
                "invariants": ["no_auto_act", "no_auto_commit", "no_auto_push"],
                "reason": f"world action '{kw}' — commands-only output, never auto-executed",
            }

    if ir["intent_type"] == "unknown" or "intent" in ir.get("missing", []):
        return {
            "verdict": "CLARIFY",
            "matched": None,
            "invariants": ["bounded_output"],
            "reason": "intent not resolvable deterministically — clarification is cheaper than inference",
        }

    return {
        "verdict": "ALLOW",
        "matched": None,
        "invariants": ["bounded_output"],
        "reason": "within frame",
    }
