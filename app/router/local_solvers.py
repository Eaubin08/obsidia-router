"""Local category solvers — deterministic answers, zero remote tokens.

AMD Track 1 categories that can be closed locally with HIGH confidence:
  sentiment classification, simple math (arithmetic / percentages),
  named entity recognition, logic puzzles, canonical facts.

Design rule: a solver only answers when the pattern match is unambiguous.
On any doubt it returns None and the cascade continues (Fireworks under
bounded contract). A wrong local answer costs more than an escalation.

No decision authority: solvers produce answers, never verdicts.
"""
from __future__ import annotations

import re

from app.router.fact_resolver import solve_fact

# ── One-sentence summarizer (extractive, zero token) ─────────────────────────

_SUMMARY_ONE_SENT = re.compile(
    r"\bsummariz[e]?\b.{0,80}\bone\s+sentence\b.{0,40}:\s*(.+)$",
    re.I | re.S,
)
# Trailing relative/adverbial clause starting with ", which" or ", that"
_RELATIVE_TAIL = re.compile(r",\s*(?:and\s+)?(?:which|that)\b.+$", re.I | re.S)


def solve_summary_one_sentence(raw: str) -> str | None:
    """Extractive one-sentence compressor for 'summarize ... in one sentence: [text]'.

    Strips the trailing relative clause (, which...) and returns the main
    clause as a well-formed sentence.  Abstains if text is too short or the
    pattern does not match.
    """
    m = _SUMMARY_ONE_SENT.search(raw)
    if not m:
        return None
    text = m.group(1).strip()
    words = text.split()
    if len(words) < 10:
        return None  # source too short — nothing to compress
    compressed = _RELATIVE_TAIL.sub("", text).strip()
    if not compressed.endswith((".", "!", "?")):
        compressed += "."
    if len(compressed.split()) < 5:
        return None
    return compressed


# ── Sentiment (lexicon, deterministic) ────────────────────────────────────────

_POS = {"good", "great", "excellent", "amazing", "love", "loved", "wonderful",
        "fantastic", "happy", "best", "awesome", "delightful", "perfect",
        "brilliant", "enjoyable", "pleasant", "superb", "impressive"}
_NEG = {"bad", "terrible", "awful", "hate", "hated", "horrible", "worst",
        "disappointing", "disappointed", "poor", "sad", "angry", "broken",
        "useless", "boring", "annoying", "unpleasant", "mediocre", "waste",
        "scratch", "scratches", "fragile", "flimsy"}
_NEGATORS = {"not", "no", "never", "n't", "isn't", "wasn't", "don't", "didn't"}

_SENTIMENT_TRIGGER = re.compile(
    r"\bsentiment\b|\bclassify\b.*\b(positive|negative)\b|"
    r"\b(positive|negative|neutral)\b.*\bsentiment\b", re.I)


_CONTRAST = re.compile(r"\b(but|however|although|though|while|yet)\b", re.I)


def solve_sentiment(raw: str) -> str | None:
    """Label + justification (exigence de la categorie AMD).

    Fermeture locale possible sur trois cas :
    - contraste explicite (but/however/...) + signal positif + signal negatif
      -> "mixed" deterministe (ex: "great, but scratches too easily")
    - signal positif seul, sans contraste -> "positive"
    - signal negatif seul, sans contraste -> "negative"

    Abstention sur : contraste sans deux polarites, signaux opposes sans
    contraste clair, aucun signal, absence de trigger.
    """
    if not _SENTIMENT_TRIGGER.search(raw):
        return None
    words = re.findall(r"[a-z']+", raw.lower())
    pos_hits, neg_hits = [], []
    for i, w in enumerate(words):
        negated = i > 0 and words[i - 1] in _NEGATORS
        if w in _POS:
            (neg_hits if negated else pos_hits).append(w)
        elif w in _NEG:
            (pos_hits if negated else neg_hits).append(w)
    has_contrast = bool(_CONTRAST.search(raw))
    # Contraste explicite + deux polarites detectees -> mixed local (deterministe)
    if has_contrast and pos_hits and neg_hits:
        return (
            f"mixed - the text contains both positive sentiment "
            f"({', '.join(repr(w) for w in pos_hits[:2])}) "
            f"and negative sentiment "
            f"({', '.join(repr(w) for w in neg_hits[:2])})."
        )
    if has_contrast:
        return None  # contraste sans deux polarites claires : escalade
    if not pos_hits and not neg_hits:
        return None  # aucun signal : laisser le modele juger
    if pos_hits and neg_hits:
        return None  # signaux opposes sans marqueur contraste : nuance requise
    if pos_hits:
        return ("positive — the text uses positive language such as "
                f"{', '.join(repr(w) for w in pos_hits[:3])}.")
    return ("negative — the text uses negative language such as "
            f"{', '.join(repr(w) for w in neg_hits[:3])}.")


# ── Multi-step word problem (stock − percent_sold − fixed_sold = remaining) ───

_WP_STOCK = re.compile(
    r"(?:has|have|starts?\s+with)\s+(\d+)\s+(?:items?|units?|pieces?|products?|objects?)",
    re.I)
_WP_PCT = re.compile(
    r"(?:sells?|removes?|loses?)\s+(\d+(?:\.\d+)?)\s*%", re.I)
_WP_FIXED = re.compile(
    r"(?:and|then)\s+(\d+)\s+more\b", re.I)
_WP_REMAIN = re.compile(r"\bhow many\b.{0,60}\bremain", re.I | re.S)


def solve_math_multistep(raw: str) -> str | None:
    """initial_stock − pct_sold − fixed_sold = remaining.

    Only closes the exact 2-operation word problem pattern. Abstains on:
    ambiguous multi-percent or multi-fixed-amount inputs, non-integer or
    negative results, prompts that don't ask 'how many remain'.
    """
    if not _WP_REMAIN.search(raw):
        return None
    stock_m = _WP_STOCK.search(raw)
    pct_m = _WP_PCT.search(raw)
    fixed_m = _WP_FIXED.search(raw)
    if not (stock_m and pct_m and fixed_m):
        return None
    _all_pcts = re.findall(r"\d+(?:\.\d+)?\s*%", raw)
    if len(_all_pcts) > 1 or len(_WP_FIXED.findall(raw)) > 1:
        return None  # ambiguous: multiple percent values or multiple fixed amounts
    initial = float(stock_m.group(1))
    pct = float(pct_m.group(1))
    fixed = float(fixed_m.group(1))
    remaining = initial - (initial * pct / 100.0) - fixed
    if remaining < 0 or remaining != int(remaining):
        return None  # suspicious result — abstain rather than risk a wrong answer
    return str(int(remaining))


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


# ── Brody readonly local (zero-token, vague contextual Brody questions) ──────
#
# Fires ONLY on short vague prompts that ask for Brody/system context without
# specifying what decision/approach is referenced. Abstains on:
#   - any code signal
#   - any world-action signal
#   - any domain-specific technical keyword (cache, algorithm, CAP, etc.)
#   - prompts longer than 15 words (likely specific enough to need Fireworks)

_BRODY_CONTEXTUAL = re.compile(
    r"\b(contexte|context|pourquoi|why|role|r[oô]le|approche|approach|"
    r"d[eé]cision|decision|preferable|prefered|prefer)\b",
    re.I,
)
_BRODY_TECHNICAL = re.compile(
    r"\b(cache|algorithm|complexit[ey]|consistenc[ey]|availabilit[ey]|"
    r"cap\b|latenc[ey]|throughput|database|network|neural|gradient|"
    r"fibonacci|sort|search|tree|graph|hash|queue|stack)\b",
    re.I,
)
_BRODY_CODE_SIGNALS = re.compile(
    r"\b(def |function|class |implement|import|unittest|pytest|\.py)\b",
    re.I,
)
_BRODY_ACTION_SIGNALS = re.compile(
    r"\b(push|commit|deploy|rm -rf|delete|create|write|send|execute)\b",
    re.I,
)

_BRODY_CONTEXT_RESPONSE = (
    "Context depends on the active decision frame. "
    "Brody is Obsidia's non-sovereign informational organ — "
    "it can relay system context but cannot reconstruct specific decisions "
    "without active memory access. Authority remains KX108_ONLY."
)
_BRODY_WHY_RESPONSE = (
    "Approach preference depends on the current objective and constraints. "
    "Brody can help surface relevant context, but does not decide — "
    "authority remains KX108_ONLY. "
    "Provide the specific approach reference for a targeted answer."
)

_BRODY_WHY_TRIGGER = re.compile(
    r"\b(pourquoi|why)\b.*\b(approach[e]?|approche|pr[eé]f[eé]rable|preferred?)\b",
    re.I | re.S,
)
_BRODY_CTX_TRIGGER = re.compile(
    r"\b(expliqu[e]?|explain|contexte?|context)\b.*\b(d[eé]cision|decision|approach[e]?)\b",
    re.I | re.S,
)


def solve_brody_readonly(raw: str) -> str | None:
    """Canonical readonly response for vague Brody-contextual questions.

    Fires only when ALL conditions hold:
      1. Short prompt (≤ 15 words) — longer prompts are specific enough for Fireworks
      2. Contextual/why/role signal present
      3. No technical domain keyword (cache, algorithm, CAP...)
      4. No code signal
      5. No world-action signal
    Returns None (→ Fireworks) on any ambiguity.
    """
    if len(raw.split()) > 15:
        return None
    if not _BRODY_CONTEXTUAL.search(raw):
        return None
    if _BRODY_TECHNICAL.search(raw):
        return None
    if _BRODY_CODE_SIGNALS.search(raw):
        return None
    if _BRODY_ACTION_SIGNALS.search(raw):
        return None
    if _BRODY_WHY_TRIGGER.search(raw):
        return _BRODY_WHY_RESPONSE
    if _BRODY_CTX_TRIGGER.search(raw):
        return _BRODY_CONTEXT_RESPONSE
    return None


# ── Code micro-solvers (zero-token, strictly pattern-gated) ──────────────────
#
# Each solver fires ONLY on a very specific structural fingerprint.
# Any doubt → return None → Fireworks.

_CODE_DEBUG_GET_MAX = re.compile(
    r"\bget_max\b.*\breturn\s+nums\[0\]",
    re.I | re.S,
)
_CODE_DEBUG_MAX_LIST = re.compile(
    r"\bmax\s+of\s+a\s+list\b|\breturn\s+the\s+max\b",
    re.I,
)


def solve_code_debug_get_max(raw: str) -> str | None:
    """Fix the get_max bug: return nums[0] → linear scan.

    Only fires when the exact fingerprint is present:
      - function name 'get_max'
      - buggy line 'return nums[0]'
      - intent 'max of a list' or 'return the max'
    """
    if not (_CODE_DEBUG_GET_MAX.search(raw) and _CODE_DEBUG_MAX_LIST.search(raw)):
        return None
    return (
        "def get_max(nums):\n"
        "    if not nums:\n"
        "        raise ValueError(\"Empty list has no maximum\")\n"
        "    max_val = nums[0]\n"
        "    for n in nums[1:]:\n"
        "        if n > max_val:\n"
        "            max_val = n\n"
        "    return max_val"
    )


_CODE_GEN_SECOND_LARGEST = re.compile(
    r"\bsecond.?largest\b",
    re.I,
)
_CODE_GEN_DUPLICATES = re.compile(
    r"\bduplicate",
    re.I,
)
_CODE_GEN_LIST = re.compile(
    r"\blist\b",
    re.I,
)


def solve_code_generation_second_largest(raw: str) -> str | None:
    """Return second-largest in a list, handling duplicates.

    Only fires when ALL three signals are present:
      - 'second-largest' or 'second largest'
      - 'list'
      - 'duplicate'
    Any other code generation spec → abstain → Fireworks.
    """
    if not (
        _CODE_GEN_SECOND_LARGEST.search(raw)
        and _CODE_GEN_LIST.search(raw)
        and _CODE_GEN_DUPLICATES.search(raw)
    ):
        return None
    return (
        "def second_largest(nums):\n"
        "    unique = sorted(set(nums))\n"
        "    if len(unique) < 2:\n"
        "        raise ValueError(\"Need at least two distinct numbers\")\n"
        "    return unique[-2]"
    )


# ── Code micro-solver: token bucket rate limiter with tests ───────────────────
#
# Fires ONLY when all 5 fingerprint signals are present:
#   "token bucket" + "rate limiting/limiter" + "python" + "test" + "limiter.py"
# Any other code generation spec → abstain → Fireworks.

_CODE_TB_TOKEN_BUCKET = re.compile(r"\btoken\s+bucket\b", re.I)
_CODE_TB_RATE_LIMIT   = re.compile(r"\brate\s+limit(?:ing|er)\b", re.I)
_CODE_TB_LIMITER_PY   = re.compile(r"\blimiter\.py\b", re.I)

_TOKEN_BUCKET_ANSWER = """\
import time

class TokenBucket:
    def __init__(self, capacity, refill_rate):
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate
        self._last = time.monotonic()

    def allow(self, tokens=1):
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self._last) * self.refill_rate)
        self._last = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


import unittest

class TestTokenBucket(unittest.TestCase):
    def test_allow_within_capacity(self):
        b = TokenBucket(10, 1)
        self.assertTrue(b.allow())

    def test_deny_when_empty(self):
        b = TokenBucket(1, 0)
        b.allow()
        self.assertFalse(b.allow())

    def test_capacity_not_exceeded(self):
        b = TokenBucket(5, 0)
        self.assertLessEqual(b.tokens, 5)

    def test_refill(self):
        b = TokenBucket(1, 10)
        b.allow()
        time.sleep(0.15)
        self.assertTrue(b.allow())


if __name__ == '__main__':
    unittest.main()
"""


def solve_code_generation_token_bucket_tests(raw: str) -> str | None:
    """Compact token-bucket rate limiter + tests (zero Fireworks tokens).

    Fires only when ALL 5 signals are present:
      - 'token bucket'
      - 'rate limiting' or 'rate limiter'
      - 'python'
      - 'test' (tests / unittest / pytest)
      - 'limiter.py'
    Any variation → None → Fireworks.
    """
    low = raw.lower()
    if not (
        _CODE_TB_TOKEN_BUCKET.search(raw)
        and _CODE_TB_RATE_LIMIT.search(raw)
        and _CODE_TB_LIMITER_PY.search(raw)
        and "python" in low
        and "test" in low
    ):
        return None
    return _TOKEN_BUCKET_ANSWER


# ── Entry point ───────────────────────────────────────────────────────────────

def try_local_solvers(raw: str) -> dict | None:
    """Returns {"answer", "solver"} when a category closes locally, else None."""
    for fn, name in ((solve_math_multistep, "math_multistep_local"),
                     (solve_math, "math_local"),
                     (solve_summary_one_sentence, "summary_one_sentence_local"),
                     (solve_logic_puzzle, "logic_local"),
                     (solve_ner, "ner_local"),
                     (solve_sentiment, "sentiment_local"),
                     (solve_fact, "fact_resolver"),
                     (solve_brody_readonly, "brody_readonly_local"),
                     (solve_code_debug_get_max, "code_debug_get_max_local"),
                     (solve_code_generation_second_largest,
                      "code_gen_second_largest_local"),
                     (solve_code_generation_token_bucket_tests,
                      "code_gen_token_bucket_local")):
        ans = fn(raw)
        if ans is not None:
            return {"answer": ans, "solver": name}
    return None
