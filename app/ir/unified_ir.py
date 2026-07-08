"""UnifiedInputIR — deterministic translation of natural language into a
structured, governable intent BEFORE any model is called.

Extracted and adapted from the Obsidia X-108 terminal (OS Langage Uni V1).
Pure function layer:
  - no subprocess
  - no network
  - no mutation
  - no authority decision (the gates + router decide, not the IR)
"""
from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> str:
    """Accent-fold, lowercase, collapse whitespace. Deterministic."""
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", folded.lower()).strip()


def _words(normalized: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", normalized))


# Keyword tables (FR + EN). These are the deterministic "compiler" tables:
# they turn free-form language into intent structure without inference.
_STATUS_WORDS = {
    "status", "statut", "etat", "state", "health", "sante", "ping", "version",
}
_CODE_WORDS = {
    "code", "coder", "patch", "implemente", "implement", "fix", "corrige",
    "refactor", "script", "fonction", "function", "write", "ecris",
}
_PLAN_WORDS = {
    "plan", "roadmap", "etapes", "steps", "organise", "planifie", "suite",
    "continue", "reprendre",
}
_AUDIT_WORDS = {
    "audit", "verifie", "verify", "check", "inspecte", "inspect", "review",
    "diagnostique", "diagnose", "coherence", "contradiction",
}
_QUESTION_WORDS = {
    "explique", "explain", "pourquoi", "why", "comment", "how", "quoi",
    "what", "contexte", "context", "resume", "summarize", "definis", "define",
}
_REASONING_WORDS = {
    "prouve", "prove", "demontre", "raisonne", "analyse", "analyze",
    "compare", "optimise", "optimize", "derive", "calcule", "compute",
    "traduis", "translate", "genere", "generate", "redige", "draft",
}
# Words that signal an action on the world (execution, git, deletion...).
# These NEVER go to a model directly: they hit the gates first.
_ACTION_WORDS = {
    "execute", "run", "lance", "push", "commit", "deploy", "deploie",
    "delete", "supprime", "rm", "install", "installe", "format", "drop",
    "autorise", "authorize", "act",
}

_LAYER_KEYWORDS: tuple[tuple[str, set[str]], ...] = (
    # Obsidure is a proper noun — highest priority.
    ("obsidure", {"obsidure"}),
    # Domain keywords are highly specific; they must beat generic words like "route".
    ("domain", {"bank", "trading", "virement", "bancaire", "gps", "altitude", "aviation"}),
    ("terminal", {"terminal", "langage", "uni", "ir", "router", "route"}),
    ("memory", {"memoire", "memory", "corpus", "souviens", "remember", "sait"}),
    ("brody", {"brody", "explique", "contexte", "reformule", "synthese"}),
    ("proof", {"preuve", "proof", "lean", "tla", "merkle", "theoreme", "invariant"}),
    ("system", {"status", "statut", "etat", "state", "health", "version"}),
    ("world", {"push", "commit", "execute", "deploy", "delete", "install", "run"}),
)


def _target_layer(words: set[str]) -> str:
    for layer, kws in _LAYER_KEYWORDS:
        if words & kws:
            return layer
    return "unknown"


def build_ir(raw: str) -> dict:
    """Build UnifiedInputIR from a free-form user input.

    Returns intent_type, target_layer, action_type, risk_level, needs,
    constraints and missing. The IR describes; it does not decide.
    """
    normalized = normalize(raw)
    words = _words(normalized)
    target_layer = _target_layer(words)

    is_action = bool(words & _ACTION_WORDS)
    is_status = bool(words & _STATUS_WORDS)
    is_code = bool(words & _CODE_WORDS)
    is_plan = bool(words & _PLAN_WORDS)
    is_audit = bool(words & _AUDIT_WORDS)
    is_question = bool(words & _QUESTION_WORDS)
    is_reasoning = bool(words & _REASONING_WORDS)

    if is_action:
        intent_type, action_type, risk_level = "world_action", "act_request", "high"
        target_layer = "world"
    elif is_status:
        intent_type, action_type, risk_level = "status", "status", "low"
    elif is_code:
        intent_type, action_type, risk_level = "code_request", "commands", "medium"
    elif is_audit:
        intent_type, action_type, risk_level = "audit", "read", "medium"
    elif is_plan:
        intent_type, action_type, risk_level = "plan", "guide", "low"
    elif is_reasoning:
        intent_type, action_type, risk_level = "reasoning", "answer", "low"
    elif is_question:
        intent_type, action_type, risk_level = "question", "answer", "low"
        if target_layer == "unknown":
            target_layer = "brody"
    else:
        intent_type, action_type, risk_level = "unknown", "guide", "low"
        if target_layer == "brody":
            # An unresolved verb aimed at the brody layer is semantic work
            # for the local organ (capabilities, context, rephrasing) — not
            # a CLARIFY dead-end. Keeps brody reachable without a keyword hit.
            intent_type, action_type = "question", "answer"

    needs = {
        "local_structure": True,
        "memory": target_layer == "memory",
        "brody": intent_type in {"question"} or target_layer == "brody",
        "remote_model": intent_type in {"reasoning", "code_request"},
        "gate": action_type in {"act_request", "commands"} or risk_level in {"medium", "high"},
    }

    constraints = [
        "router_non_sovereign",
        "no_auto_act",
        "no_auto_commit",
        "no_auto_push",
        "bounded_output",
    ]

    missing: list[str] = []
    if intent_type == "code_request" and not (words & {"fichier", "file", "test", "scope"}):
        missing.append("target_scope")
    if intent_type == "unknown":
        missing.append("intent")
    if target_layer == "unknown" and intent_type not in {"reasoning", "unknown"}:
        missing.append("target_layer")

    return {
        "raw": raw,
        "normalized": normalized,
        "intent_type": intent_type,
        "target_layer": target_layer,
        "action_type": action_type,
        "risk_level": risk_level,
        "needs": needs,
        "constraints": constraints,
        "missing": missing,
    }


def format_ir(ir: dict) -> str:
    active = [k for k, v in ir.get("needs", {}).items() if v]
    lines = [
        "UnifiedInputIR",
        f"  intent_type : {ir['intent_type']}",
        f"  target_layer: {ir['target_layer']}",
        f"  action_type : {ir['action_type']}",
        f"  risk_level  : {ir['risk_level']}",
        f"  needs       : {', '.join(active) if active else 'none'}",
    ]
    if ir.get("missing"):
        lines.append(f"  missing     : {', '.join(ir['missing'])}")
    return "\n".join(lines)
