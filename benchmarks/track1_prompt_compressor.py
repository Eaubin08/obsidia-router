"""Frontier prompt compressor for remote Fireworks escalations.

Format instructions (Answer only, Code only, Max 3 bullets...) are carried
by compact_system via build_compact_override(). This module only strips
noise from the user message -- it never duplicates those instructions.

Compression steps:
  1. Strip jailbreak role-playing prefixes  ("tu es ... sans restrictions,")
  2. Strip ignore-instructions suffixes     ("... et ignore tout le reste")
  3. Strip politeness suffixes              ("... stp", "... please")
  4. Strip English meta-request fillers     ("Can you ...", "Please ...")
  5. Safety fallback: if result < 8 chars, revert to original
  6. Check inline code for CITER spans     (code_file only)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.router.local_solvers import extract_citer_spans

_RE_JAILBREAK_PREFIX = re.compile(
    r"^(?:tu es\s+[^,\.]{1,80}[,\.]\s*|you are\s+[^,\.]{1,80}[,\.]\s*)",
    re.IGNORECASE,
)
_RE_IGNORE_SUFFIX = re.compile(
    r"\s+(?:et\s+)?ignore(?:z)?\s+(?:tout\s+le\s+)?(?:le\s+)?reste\b[\.\!]?\s*$",
    re.IGNORECASE,
)
_RE_POLITENESS_SUFFIX = re.compile(
    r"\s+(?:stp|svp|please|merci|thanks?|thank\s+you)[\.\!]?\s*$",
    re.IGNORECASE,
)
_RE_META_FILLER_PREFIX = re.compile(
    r"^(?:can\s+you\s+|could\s+you\s+|please\s+|i\s+need\s+you\s+to\s+"
    r"|i\s+want\s+you\s+to\s+|i\s+would\s+like\s+you\s+to\s+)",
    re.IGNORECASE,
)

_MIN_COMPRESSED_LEN = 8


def build_frontier_remote_prompt(
    prompt: str,
    answer_kind: str,
    task_id: str | None = None,
    family: str | None = None,
) -> tuple[str, dict]:
    """Strip noise from user prompt before a frontier Fireworks call.

    Never adds content. Returns (compressed_prompt, metrics_dict).
    """
    original_len = len(prompt)
    stripped = prompt
    stripped = _RE_JAILBREAK_PREFIX.sub("", stripped).strip()
    stripped = _RE_IGNORE_SUFFIX.sub("", stripped).strip()
    stripped = _RE_POLITENESS_SUFFIX.sub("", stripped).strip()
    stripped = _RE_META_FILLER_PREFIX.sub("", stripped).strip()

    if len(stripped) < _MIN_COMPRESSED_LEN:
        stripped = prompt.strip()

    stripped_len = len(stripped)

    citer_used = False
    if answer_kind == "code_file":
        spans = extract_citer_spans(stripped)
        if spans:
            citer_used = True
            stripped = stripped.rstrip() + "\n\nKey spans:\n" + "\n".join(spans)

    compressed = stripped
    compressed_len = len(compressed)
    compression_applied = stripped_len < original_len

    return compressed, {
        "prompt_chars_before":        original_len,
        "prompt_chars_after":         compressed_len,
        "stripped_chars":             original_len - stripped_len,
        "prompt_compression_applied": compression_applied,
        "compression_ratio":          round(compressed_len / max(original_len, 1), 3),
        "citer_used":                 citer_used,
    }
