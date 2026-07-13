"""Output validation for Track 3 model responses.

Single deterministic repair pass — no second model call.
If still invalid after repair: status=unresolved.

Validated properties:
  - Non-empty
  - Max length bounded (3000 chars)
  - Reasoning blocks stripped (chain-of-thought leakage)
  - Error markers detected and rejected
"""
from __future__ import annotations

import re

_MAX_CHARS = 3000

# Reasoning block delimiters that should never appear in a public answer
_REASONING_PAIRS = [
    ("<thinking>",  "</thinking>"),
    ("<scratchpad>", "</scratchpad>"),
    ("[INTERNAL]",  "[/INTERNAL]"),
    ("[HIDDEN]",    "[/HIDDEN]"),
]

# Error markers — if present after repair, reject
_ERROR_MARKERS = [
    "Traceback (most recent call last):",
    "[INTERNAL ERROR]",
    "RuntimeError:",
    "ValueError:",
    "KeyError:",
]

# Private reasoning markers — single-line, strip the whole line
_PRIVATE_LINE_PATTERNS = [
    re.compile(r"^.*chain[_\s]of[_\s]thought.*$", re.I | re.M),
    re.compile(r"^.*hidden[_\s]state.*$", re.I | re.M),
    re.compile(r"^.*\[REASONING\].*$", re.I | re.M),
]


def _strip_reasoning_blocks(text: str) -> tuple[str, bool]:
    """Strip paired reasoning block markers. Returns (cleaned, was_repaired)."""
    cleaned = text
    repaired = False
    for opener, closer in _REASONING_PAIRS:
        while opener in cleaned:
            start = cleaned.find(opener)
            end = cleaned.find(closer, start)
            if end == -1:
                # Unclosed block — strip from opener to end
                cleaned = cleaned[:start].strip()
            else:
                cleaned = (cleaned[:start] + cleaned[end + len(closer):]).strip()
            repaired = True
    for pattern in _PRIVATE_LINE_PATTERNS:
        new_text = pattern.sub("", cleaned).strip()
        if new_text != cleaned:
            cleaned = new_text
            repaired = True
    return cleaned, repaired


def validate_and_repair(answer: str, capability_id: str = "") -> dict:
    """Validate and optionally repair a model output.

    Returns:
        {
            "valid":    bool,
            "answer":   str,       # repaired or original
            "repaired": bool,
            "reason":   str|None,  # non-None only when invalid
        }

    Repair is deterministic and applied at most once.
    No second model call is ever made.
    """
    if not answer or not answer.strip():
        return {"valid": False, "answer": "", "repaired": False, "reason": "empty_answer"}

    # ── Single repair pass ────────────────────────────────────────────────────
    working, was_repaired = _strip_reasoning_blocks(answer)

    # Truncate at max length (bounded output contract)
    if len(working) > _MAX_CHARS:
        working = working[:_MAX_CHARS].rsplit(" ", 1)[0] if " " in working[:_MAX_CHARS] else working[:_MAX_CHARS]
        was_repaired = True

    working = working.strip()

    # ── Post-repair checks ────────────────────────────────────────────────────
    if not working:
        return {"valid": False, "answer": "", "repaired": was_repaired, "reason": "empty_after_repair"}

    for marker in _ERROR_MARKERS:
        if marker in working:
            return {
                "valid":    False,
                "answer":   working,
                "repaired": was_repaired,
                "reason":   f"error_marker_detected: {marker!r}",
            }

    return {"valid": True, "answer": working, "repaired": was_repaired, "reason": None}
