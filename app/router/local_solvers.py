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


_CONTRAST = re.compile(r"\b(but|however|although|though|while|yet)\b", re.I)


def solve_sentiment(raw: str) -> str | None:
    """Label + justification (exigence de la categorie AMD).

    Abstention systematique sur les cas nuances : signaux mixtes, marqueur
    de contraste (but/however/...), ou signal opposant present — le juge
    LLM attend de la nuance que le lexique ne peut pas garantir.
    """
    if not _SENTIMENT_TRIGGER.search(raw):
        return None
    if _CONTRAST.search(raw):
        return None  # avis contraste (ex: "great, but...") : nuance requise
    words = re.findall(r"[a-z']+", raw.lower())
    pos_hits, neg_hits = [], []
    for i, w in enumerate(words):
        negated = i > 0 and words[i - 1] in _NEGATORS
        if w in _POS:
            (neg_hits if negated else pos_hits).append(w)
        elif w in _NEG:
            (pos_hits if negated else neg_hits).append(w)
    if not pos_hits and not neg_hits:
        return None  # aucun signal : laisser le modele juger
    if pos_hits and neg_hits:
        return None  # signaux opposes : nuance requise, escalade
    if pos_hits:
        return ("positive — the text uses positive language such as "
                f"{', '.join(repr(w) for w in pos_hits[:3])}.")
    return ("negative — the text uses negative language such as "
            f"{', '.join(repr(w) for w in neg_hits[:3])}.")


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


# ── Named entity recognition (rule-based, abstain on any doubt) ──────────────

_MONTHS = {"january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"}
_ORG_SUFFIX = {"AI", "Inc", "Inc.", "Corp", "Corp.", "Ltd", "Ltd.", "LLC",
               "GmbH", "University", "Institute", "Company", "Labs", "Group"}
_KNOWN_PLACES = {"berlin", "paris", "london", "tokyo", "madrid", "rome",
                 "amsterdam", "vienna", "dublin", "lisbon", "brussels",
                 "munich", "zurich", "geneva", "sydney", "toronto", "austin",
                 "seattle", "boston", "chicago", "france", "germany", "spain",
                 "italy", "japan", "canada", "australia", "europe", "usa"}

_NER_TRIGGER = re.compile(r"\bextract\b.*\bentit|named entit", re.I)


def solve_ner(raw: str) -> str | None:
    m = re.search(r"from\s*:\s*(.+)$", raw, re.I | re.S)
    if not (_NER_TRIGGER.search(raw) and m):
        return None
    text = m.group(1).strip()
    tokens = re.findall(r"[A-Za-z][A-Za-z']*\.?", text)
    tokens = [t.rstrip(".") if t.rstrip(".") not in _ORG_SUFFIX else t
              for t in tokens]
    entities: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        if tokens[i][0].isupper():
            group = [tokens[i]]
            while i + 1 < len(tokens) and tokens[i + 1][0].isupper():
                i += 1
                group.append(tokens[i])
            name = " ".join(group)
            low = name.lower()
            if low in _MONTHS:
                entities.append((name, "DATE"))
            elif low in _KNOWN_PLACES:
                entities.append((name, "LOCATION"))
            elif group[-1] in _ORG_SUFFIX:
                entities.append((name, "ORGANIZATION"))
            elif len(group) >= 2:
                entities.append((name, "PERSON"))
            else:
                return None  # entite inclassable avec certitude -> escalade
        i += 1
    if not entities:
        return None
    return "; ".join(f"{n} - {k}" for n, k in entities)


# ── Logical deduction (constraint puzzle by enumeration) ─────────────────────

_PUZZLE_ITEMS = re.compile(
    r"each\s+owns?\s+a\s+different\s+\w+\s*:\s*([\w\s,]+?)(?:\.|$)", re.I)
_C_NEG = re.compile(r"(\w+)\s+does\s+not\s+own\s+the\s+(\w+)", re.I)
_C_POS = re.compile(r"(\w+)\s+owns\s+the\s+(\w+)", re.I)
_Q_WHO = re.compile(r"who\s+owns\s+the\s+(\w+)", re.I)


def solve_logic_puzzle(raw: str) -> str | None:
    from itertools import permutations
    items_m, who_m = _PUZZLE_ITEMS.search(raw), _Q_WHO.search(raw)
    if not (items_m and who_m):
        return None
    items = [w.strip().lower() for w in re.split(r",|\band\b", items_m.group(1))
             if w.strip()]
    target = who_m.group(1).lower()
    if target not in items or len(items) < 2:
        return None
    neg = [(a.lower(), b.lower()) for a, b in _C_NEG.findall(raw)]
    # "does not own" matche aussi _C_POS ("not own the X" contient "own the") :
    # une paire presente en negatif ne peut pas etre un positif.
    pos = [(a.lower(), b.lower()) for a, b in _C_POS.findall(raw)
           if (a.lower(), b.lower()) not in neg
           and a.lower() not in ("not", "who", "which", "whoever")]
    pos = [p for p in pos if p[1] in items]
    neg = [n for n in neg if n[1] in items]
    if not (pos or neg):
        return None
    # Les proprietaires : les noms capitalises du texte qui apparaissent
    # dans les contraintes, completes par les autres capitalises non-items.
    caps = []
    for w in re.findall(r"\b[A-Z][a-z]+\b", raw):
        lw = w.lower()
        if lw not in caps and lw not in items and lw not in (
                "three", "who", "the", "each", "friends", "and"):
            caps.append(lw)
    constraint_names = {a for a, _ in pos + neg}
    if not constraint_names.issubset(set(caps)):
        return None
    names = caps[:len(items)]
    if len(names) != len(items):
        return None
    solutions = []
    for perm in permutations(items):
        assign = dict(zip(names, perm))
        if all(assign.get(a) == b for a, b in pos) and \
           all(assign.get(a) != b for a, b in neg):
            solutions.append(assign)
    if len(solutions) != 1:
        return None  # zero ou plusieurs solutions : escalade
    owner = next(n for n, it in solutions[0].items() if it == target)
    return f"{owner.capitalize()} owns the {target}."


# ── Entry point ───────────────────────────────────────────────────────────────

def try_local_solvers(raw: str) -> dict | None:
    """Returns {"answer", "solver"} when a category closes locally, else None."""
    for fn, name in ((solve_math, "math_local"),
                     (solve_logic_puzzle, "logic_local"),
                     (solve_ner, "ner_local"),
                     (solve_sentiment, "sentiment_local")):
        ans = fn(raw)
        if ans is not None:
            return {"answer": ans, "solver": name}
    return None
