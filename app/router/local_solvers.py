"""Local category solvers — deterministic answers, zero remote tokens.

AMD Track 1 categories that can be closed locally with HIGH confidence:
  sentiment classification, simple math (arithmetic / percentages).

Design rule: a solver only answers when the pattern match is unambiguous.
On any doubt it returns None and the cascade continues (Fireworks under
bounded contract). A wrong local answer costs more than an escalation.

No decision authority: solvers produce answers, never verdicts.
"""
from __future__ import annotations

import re

# ── Sentiment (lexicon, deterministic) ────────────────────────────────────────

_POS = {"good", "great", "excellent", "amazing", "love", "loved", "wonderful",
        "fantastic", "happy", "best", "awesome", "delightful", "perfect",
        "brilliant", "enjoyable", "pleasant", "superb", "impressive"}
_NEG = {"bad", "terrible", "awful", "hate", "hated", "horrible", "worst",
        "disappointing", "disappointed", "poor", "sad", "angry", "broken",
        "useless", "boring", "annoying", "unpleasant", "mediocre", "waste"}
_NEGATORS = {"not", "no", "never", "n't", "isn't", "wasn't", "don't", "didn't"}

_SENTIMENT_TRIGGER = re.compile(
    r"\bsentiment\b|\bclassify\b.*\b(positive|negative)\b|"
    r"\b(positive|negative|neutral)\b.*\bsentiment\b", re.I)


def solve_sentiment(raw: str) -> str | None:
    if not _SENTIMENT_TRIGGER.search(raw):
        return None
    words = re.findall(r"[a-z']+", raw.lower())
    pos = neg = 0
    for i, w in enumerate(words):
        negated = i > 0 and words[i - 1] in _NEGATORS
        if w in _POS:
            pos, neg = (pos, neg + 1) if negated else (pos + 1, neg)
        elif w in _NEG:
            pos, neg = (pos + 1, neg) if negated else (pos, neg + 1)
    if pos == neg == 0:
        return None  # aucun signal : laisser le modele juger
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


# ── Simple math (arithmetic / percentages) ────────────────────────────────────

_ARITH = re.compile(
    r"(?:what is|calculate|compute|combien fait)?\s*"
    r"(-?\d+(?:\.\d+)?)\s*([+\-*/x×])\s*(-?\d+(?:\.\d+)?)\s*[=?]?\s*$", re.I)
_PERCENT = re.compile(
    r"(?:what is|calculate|compute)?\s*(\d+(?:\.\d+)?)\s*%\s*of\s*"
    r"(-?\d+(?:\.\d+)?)", re.I)


def _fmt(x: float) -> str:
    return str(int(x)) if x == int(x) else f"{x:.4f}".rstrip("0").rstrip(".")


def solve_math(raw: str) -> str | None:
    m = _PERCENT.search(raw)
    if m:
        p, base = float(m.group(1)), float(m.group(2))
        return _fmt(p / 100.0 * base)
    m = _ARITH.search(raw.strip())
    if m:
        a, op, b = float(m.group(1)), m.group(2), float(m.group(3))
        if op in ("x", "×"):
            op = "*"
        if op == "/" and b == 0:
            return None
        val = {"+": a + b, "-": a - b, "*": a * b, "/": a / b}[op]
        return _fmt(val)
    return None


# ── Entry point ───────────────────────────────────────────────────────────────

def try_local_solvers(raw: str) -> dict | None:
    """Returns {"answer", "solver"} when a category closes locally, else None."""
    ans = solve_math(raw)
    if ans is not None:
        return {"answer": ans, "solver": "math_local"}
    ans = solve_sentiment(raw)
    if ans is not None:
        return {"answer": ans, "solver": "sentiment_local"}
    return None
