"""Semantic topic router — maps a free-form message to a canonical topic
without calling any model.

Adapted from the Obsidia Brody semantic query router. Key properties kept:
  - the reserved token ACT never matches inside French words
    (actuel, actualite, activation, transaction...)
  - short triggers require word boundaries
  - unknown queries fall back to bounded word extraction, never to a raw
    full-sentence query
"""
from __future__ import annotations

import re

from app.ir.unified_ir import normalize

# (triggers, topic)
_TOPIC_ROUTES: list[tuple[list[str], str]] = [
    (["status", "statut", "etat actuel", "ou on en est", "current state", "recap"], "CURRENT_STATE"),
    (["memoire", "memory", "corpus", "que sait", "souviens", "remember"], "MEMORY_QUERY"),
    (["preuve", "proof", "lean", "tla", "merkle", "invariant"], "PROOF_QUERY"),
    (["act", "autorise", "authorize", "execute", "push", "commit", "deploy"], "ACTION_BOUNDARY"),
    (["traduis", "translate", "langage uni", "ir", "structure ma demande"], "IR_REQUEST"),
    (["code", "patch", "fix", "implemente", "script", "fonction"], "CODE_REQUEST"),
    (["explique", "pourquoi", "comment", "resume", "analyse", "compare"], "REASONING"),
]


def _trigger_matches(trigger: str, folded: str) -> bool:
    if " " in trigger:
        return trigger in folded
    if len(trigger) <= 3:
        return re.search(rf"(?<![a-z0-9]){re.escape(trigger)}(?![a-z0-9])", folded) is not None
    return trigger in folded


def route_topic(message: str) -> dict:
    folded = normalize(message)

    for triggers, topic in _TOPIC_ROUTES:
        if any(_trigger_matches(t, folded) for t in triggers):
            return {"topic": topic, "is_canonical": True, "route": "TOPIC_MATCHED"}

    words = [w for w in re.split(r"\W+", folded) if len(w) >= 4]
    return {
        "topic": "GENERAL",
        "is_canonical": False,
        "route": "FALLBACK_WORD_EXTRACTION",
        "query": " ".join(words[:3]) if words else folded[:60],
    }
