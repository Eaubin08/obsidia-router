"""Track 3 specific deterministic solvers — additive, never modifies Track 1 modules.

These solvers extend the local deterministic surface for Track 3 without
touching app/router/local_solvers.py (which is shared with Track 1).

Entry point: try_t3_solvers(raw) — same interface as Track 1's try_local_solvers().
"""
from __future__ import annotations

import re

# ── Multiplication word problem ───────────────────────────────────────────────
#
# Fires on: "N <unit> with M <items> in each [unit]" + "how many"
# Example: "A warehouse has 24 boxes with 18 items in each box. How many items are there?"
# → 24 * 18 = 432
#
# Abstains on:
#   - no "how many" question
#   - multiple group/per patterns (ambiguous)
#   - non-integer result

_MULT_WP_GROUPS = re.compile(
    r"\b(?P<groups>\d+)\s+\w+\s+(?:with|of)\s+(?P<per>\d+)\s+\w+\s+in\s+each\b",
    re.I,
)
_MULT_WP_QUESTION = re.compile(r"\bhow\s+many\b", re.I)


def solve_word_multiply(raw: str) -> str | None:
    """Solve an N-groups × M-per-group multiplication word problem.

    Fires ONLY when:
      1. 'how many' question is present
      2. Exactly one 'N <unit> with M <items> in each' pattern matches

    Examples:
      "A warehouse has 24 boxes with 18 items in each box" → "432"
      "There are 12 teams with 11 players in each team" → "132"
    """
    if not _MULT_WP_QUESTION.search(raw):
        return None
    matches = list(_MULT_WP_GROUPS.finditer(raw))
    if len(matches) != 1:
        return None
    groups = int(matches[0].group("groups"))
    per    = int(matches[0].group("per"))
    result = groups * per
    return str(result)


# ── Entry point ───────────────────────────────────────────────────────────────

def try_t3_solvers(raw: str) -> dict | None:
    """Return {"answer", "solver"} when a Track 3 solver closes the request, else None."""
    for fn, name in (
        (solve_word_multiply, "word_multiply_local"),
    ):
        ans = fn(raw)
        if ans is not None:
            return {"answer": ans, "solver": name}
    return None
