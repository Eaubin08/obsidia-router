"""Track 3 memory adapter — readonly lookup in examples/memory_index.json.

Rules:
  - Read-only: no creates, no updates, no deletes.
  - Bounded keyword matching: at least MIN_KEYWORD_MATCHES distinctive
    keywords must appear in the query for a hit to be declared.
  - No fuzzy matching: exact substring presence check on lowercased text.
  - Abstains (returns None) on any doubt.
  - Never writes to disk; memory_hit never grants decision authority.

The memory_index.json is a static file loaded once per process.
Lookup is deterministic and reproducible.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

_MEMORY_PATH = Path(__file__).parents[2] / "examples" / "memory_index.json"

# Minimum number of distinctive keywords that must appear for a hit.
_MIN_KEYWORD_MATCHES = 2

# Keyword sets per memory entry key.
# Derived from the key name and value content; manually curated for precision.
_ENTRY_KEYWORDS: dict[str, set[str]] = {
    "CURRENT_STATE": {
        "current", "state", "routing", "router", "obsidia",
        "deterministic", "gates", "topic", "ir", "brody",
        "public", "cut", "inference", "layer",
    },
    "PROOF_QUERY": {
        "proof", "lean", "tla", "merkle", "seal", "governance",
        "kernel", "formal", "anchor", "proofs", "x-108",
    },
}


def _load() -> dict:
    try:
        with _MEMORY_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_INDEX: dict = _load()


def lookup(raw: str, ir: dict | None = None) -> dict | None:
    """Readonly keyword-based lookup.

    Returns:
        {
            "answer":       str,    # the stored memory value
            "source_key":   str,    # the key in memory_index.json
            "category":     str,    # "memory_readonly"
            "match_count":  int,    # how many keywords matched
            "elapsed_ms":   float,
        }
        or None when no entry is found with sufficient confidence.

    Never raises; returns None on any error.
    """
    t0 = time.perf_counter()
    try:
        q = raw.lower()
        best_key: str | None = None
        best_count: int = 0

        for key, keywords in _ENTRY_KEYWORDS.items():
            count = sum(1 for kw in keywords if kw in q)
            if count > best_count:
                best_count = count
                best_key = key

        elapsed = round((time.perf_counter() - t0) * 1000, 2)

        if best_key is None or best_count < _MIN_KEYWORD_MATCHES:
            return None

        value = _INDEX.get(best_key)
        if value is None:
            return None

        return {
            "answer":      value,
            "source_key":  best_key,
            "category":    "memory_readonly",
            "match_count": best_count,
            "elapsed_ms":  elapsed,
        }
    except Exception:
        return None
