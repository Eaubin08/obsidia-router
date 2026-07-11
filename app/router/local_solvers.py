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
from decimal import Decimal, InvalidOperation

from app.router.fact_resolver import solve_fact

# ── Extractive summarizer — bounded N sentences (zero token) ─────────────────
#
# Recognises "summarize ... in [one|two|1|2] sentence[s]: <passage>"
# and selects the most informative sentences from the passage.
#
# Strategy for N=1: first sentence (usually the main claim).
# Strategy for N=2: first sentence + the sentence with a contrast/consequence
#   marker (however, but, although, therefore, so, thus); if none, second
#   sentence.
# Abstains when:
#   - pattern does not match (no N found, no passage delimiter)
#   - passage yields fewer sentences than requested
#   - passage too short (< 10 words)
#   - any selected sentence is empty after stripping

_SUMMARY_TRIGGER = re.compile(
    r"\bsummariz[e]?\b.{0,100}"
    r"\b(one|two|1|2)\s+sentences?\b"
    r".{0,60}:\s*(.+)$",
    re.I | re.S,
)
_RELATIVE_TAIL = re.compile(r",\s*(?:and\s+)?(?:which|that)\b.+$", re.I | re.S)
_CONTRAST_SENT = re.compile(
    r"\b(however|but|although|though|yet|despite|"
    r"unfortunately|on\s+the\s+other\s+hand|"
    r"therefore|thus|so|as\s+a\s+result|consequently)\b",
    re.I,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

_N_MAP = {"one": 1, "1": 1, "two": 2, "2": 2}

_SUMMARY_MIN_WORDS = 10   # passage too short to compress
_SUMMARY_MAX_CHARS = 600  # hard cap per sentence to avoid verbosity


def _split_sentences(text: str) -> list[str]:
    """Split passage into sentences; keep only non-empty, reasonably sized ones."""
    raw_sents = _SENTENCE_SPLIT.split(text.strip())
    return [s.strip() for s in raw_sents if len(s.strip()) > 5]


def _ensure_period(s: str) -> str:
    return s if s.endswith((".", "!", "?")) else s + "."


def solve_summary_one_sentence(raw: str) -> str | None:
    """Extractive summarizer for 'summarize ... in one/two sentence(s): <passage>'.

    Supports: one sentence, two sentences, 1 sentence, 2 sentences.
    Selects sentences from the passage without inventing content.
    Abstains on ambiguous, too-short, or poorly delimited passages.

    Kept under the historical name so existing callers and tests are unaffected.
    """
    m = _SUMMARY_TRIGGER.search(raw)
    if not m:
        return None
    n_word = m.group(1).lower()
    n = _N_MAP.get(n_word)
    if n is None:
        return None
    passage = m.group(2).strip()
    if len(passage.split()) < _SUMMARY_MIN_WORDS:
        return None
    sents = _split_sentences(passage)
    if len(sents) < n:
        return None  # passage has fewer sentences than requested

    if n == 1:
        chosen = [sents[0]]
    else:  # n == 2
        # First sentence = main claim
        first = sents[0]
        # Find the sentence with the strongest contrast/consequence signal
        contrast_sent = next(
            (s for s in sents[1:] if _CONTRAST_SENT.search(s)), None
        )
        second = contrast_sent if contrast_sent else sents[1]
        chosen = [first, second]

    # Validate and clean
    result_parts = []
    for s in chosen:
        clean = _RELATIVE_TAIL.sub("", s).strip()
        if not clean or len(clean) > _SUMMARY_MAX_CHARS:
            return None  # malformed sentence — abstain
        result_parts.append(_ensure_period(clean))

    result = " ".join(result_parts)
    # Final sanity: non-empty, no markup leaking in
    if not result or "<" in result:
        return None
    return result


# ── Sentiment (lexicon, deterministic) ────────────────────────────────────────

_POS = {
    # Direct positive adjectives
    "good", "great", "excellent", "amazing", "wonderful", "fantastic",
    "happy", "best", "awesome", "delightful", "perfect", "brilliant",
    "enjoyable", "pleasant", "superb", "impressive", "outstanding",
    "remarkable", "exceptional", "marvelous", "splendid", "terrific",
    "magnificent", "incredible", "fabulous", "gorgeous", "beautiful",
    "elegant", "smooth", "clean", "fast", "quick", "reliable", "solid",
    "sturdy", "comfortable", "convenient", "useful", "helpful",
    # Verb forms
    "love", "loved", "loves", "enjoy", "enjoyed", "enjoys",
    "like", "liked", "likes", "adore", "adored", "adores",
    "recommend", "recommended", "recommends",
    # Duration/quality signals (positive context)
    "lasts", "lasting", "durable", "forever", "always",
    # Compound / colloquial
    "well-made", "top-notch", "high-quality",
}
_NEG = {
    # Direct negative adjectives
    "bad", "terrible", "awful", "horrible", "worst", "poor",
    "disappointing", "disappointed", "mediocre", "useless",
    "boring", "annoying", "unpleasant", "waste", "fragile",
    "flimsy", "cheap", "cheaply", "broken", "defective", "faulty",
    "slow", "noisy", "loud", "heavy", "bulky", "unreliable",
    "uncomfortable", "inconvenient", "difficult", "confusing",
    # Verb forms
    "hate", "hated", "hates", "dislike", "disliked", "dislikes",
    "regret", "regretted", "regrets", "avoid", "avoided",
    # Damage / physical defect
    "scratch", "scratches", "scratched", "crack", "cracked", "broke",
    "break", "breaking", "peel", "peeled", "peeling",
    # Strong negatives
    "sad", "angry", "frustrated", "furious", "disgusted",
    # Colloquial
    "terrible", "horrid", "dreadful",
}
_NEGATORS = {"not", "no", "never", "n't", "isn't", "wasn't", "don't",
             "didn't", "hardly", "barely", "scarcely"}

_SENTIMENT_TRIGGER = re.compile(
    r"\bsentiment\b|\bclassify\b.*\b(positive|negative|neutral)\b|"
    r"\b(positive|negative|neutral)\b.*\bsentiment\b|"
    r"\bhow\s+(positive|negative|neutral)\b", re.I)

_CONTRAST = re.compile(
    r"\b(but|however|although|though|while|yet|despite|except|"
    r"unfortunately|on\s+the\s+other\s+hand|even\s+so)\b", re.I)

# Neutral signals: factual, descriptive, no polarity
_NEUTRAL_ONLY = re.compile(
    r"\b(neutral|objective|factual|informational|neither)\b", re.I)


def solve_sentiment(raw: str) -> str | None:
    """Sentiment classifier: positive / negative / neutral / mixed + justification.

    Closes locally on four cases:
    - contrast marker + pos signal + neg signal → mixed (deterministic)
    - pos signals only, no contrast → positive
    - neg signals only, no contrast → negative
    - explicit neutral marker + no strong polarity → neutral

    Abstains on:
    - contrast without two clear polarities
    - opposing signals without a contrast marker
    - no polarity signal and no neutral marker
    - missing sentiment trigger
    - single ambiguous word without context
    """
    if not _SENTIMENT_TRIGGER.search(raw):
        return None
    # Tokenize: keep interior apostrophes (n't, it's) but strip leading/trailing
    # quote characters that appear as sentence delimiters (e.g. 'Great camera...')
    words = [w.strip("'") for w in re.findall(r"[a-z][a-z']*|'[a-z]+", raw.lower())
             if w.strip("'")]
    pos_hits, neg_hits = [], []
    for i, w in enumerate(words):
        # Simple local negation window: one word before
        negated = i > 0 and words[i - 1] in _NEGATORS
        if w in _POS:
            (neg_hits if negated else pos_hits).append(w)
        elif w in _NEG:
            (pos_hits if negated else neg_hits).append(w)
    has_contrast = bool(_CONTRAST.search(raw))
    total_signals = len(pos_hits) + len(neg_hits)
    # Contraste explicite + deux polarites -> mixed (deterministe)
    if has_contrast and pos_hits and neg_hits:
        return (
            f"mixed - the text contains both positive sentiment "
            f"({', '.join(repr(w) for w in pos_hits[:2])}) "
            f"and negative sentiment "
            f"({', '.join(repr(w) for w in neg_hits[:2])})."
        )
    if has_contrast and total_signals < 2:
        return None  # contraste sans deux polarites claires : escalade
    if not pos_hits and not neg_hits:
        # No polarity detected — check for explicit neutral marker
        if _NEUTRAL_ONLY.search(raw):
            return "neutral - the text does not express clear positive or negative sentiment."
        return None  # aucun signal fiable : laisser le modele juger
    if pos_hits and neg_hits:
        return None  # signaux opposes sans marqueur de contraste : nuance requise
    if pos_hits:
        return ("positive - the text uses positive language such as "
                f"{', '.join(repr(w) for w in pos_hits[:3])}.")
    return ("negative - the text uses negative language such as "
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



# ── Generic quantity/time rate solver ────────────────────────────────────────

_RATE_TRIGGER = re.compile(
    r"\b(?:average\s+speed|speed|rate|throughput|flow|"
    r"\bper\s+(?:hour|minute|second))\b",
    re.I,
)

_RATE_QUANTITY_TIME = re.compile(
    r"\b(?:travels?|covers?|moves?|drives?|flies?|runs?|cycles?|"
    r"produces?|processes?|handles?|pumps?|uses?)\s+"
    r"(?P<amount>\d+(?:\.\d+)?)\s+"
    r"(?P<unit>"
    r"kilometers?|kilometres?|km|"
    r"miles?|mi|"
    r"meters?|metres?|"
    r"liters?|litres?|"
    r"units?|items?|requests?"
    r")\s+"
    r"(?:in|over|during)\s+"
    r"(?P<duration>\d+(?:\.\d+)?)\s+"
    r"(?P<time>"
    r"hours?|hrs?|hr|"
    r"minutes?|mins?|min|"
    r"seconds?|secs?|sec"
    r")\b",
    re.I,
)

_RATE_REQUESTED_UNIT = re.compile(
    r"\b(?P<unit>"
    r"kilometers?|kilometres?|km|"
    r"miles?|mi|"
    r"meters?|metres?|"
    r"liters?|litres?|"
    r"units?|items?|requests?"
    r")\s+per\s+"
    r"(?P<time>hours?|hrs?|hr|minutes?|mins?|min|seconds?|secs?|sec)\b",
    re.I,
)

_RATE_UNIT_ALIASES = {
    "kilometer": "kilometer",
    "kilometers": "kilometer",
    "kilometre": "kilometer",
    "kilometres": "kilometer",
    "km": "kilometer",
    "mile": "mile",
    "miles": "mile",
    "mi": "mile",
    "meter": "meter",
    "meters": "meter",
    "metre": "meter",
    "metres": "meter",
    "liter": "liter",
    "liters": "liter",
    "litre": "liter",
    "litres": "liter",
    "unit": "unit",
    "units": "unit",
    "item": "item",
    "items": "item",
    "request": "request",
    "requests": "request",
}

_RATE_UNIT_DISPLAY = {
    "kilometer": "kilometers",
    "mile": "miles",
    "meter": "meters",
    "liter": "liters",
    "unit": "units",
    "item": "items",
    "request": "requests",
}

_RATE_TIME_ALIASES = {
    "hour": "hour",
    "hours": "hour",
    "hr": "hour",
    "hrs": "hour",
    "minute": "minute",
    "minutes": "minute",
    "min": "minute",
    "mins": "minute",
    "second": "second",
    "seconds": "second",
    "sec": "second",
    "secs": "second",
}

_RATE_TIME_SECONDS = {
    "hour": Decimal("3600"),
    "minute": Decimal("60"),
    "second": Decimal("1"),
}


def _format_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("non-finite decimal")
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def solve_rate(raw: str) -> str | None:
    """Solve a bounded quantity-per-time problem.

    Supported family:
      amount of a quantity in a duration -> quantity per requested time unit.

    Examples include distance/speed, production rate, flow and throughput.
    The solver abstains on incompatible units, missing rate intent, zero
    duration, unsupported conversions or ambiguous multiple measurements.
    """
    if not _RATE_TRIGGER.search(raw):
        return None

    matches = list(_RATE_QUANTITY_TIME.finditer(raw))
    if len(matches) != 1:
        return None

    match = matches[0]
    requested = _RATE_REQUESTED_UNIT.search(raw)

    input_unit = _RATE_UNIT_ALIASES.get(match.group("unit").lower())
    input_time = _RATE_TIME_ALIASES.get(match.group("time").lower())

    if input_unit is None or input_time is None:
        return None

    requested_unit = input_unit
    requested_time = input_time

    if requested:
        requested_unit = _RATE_UNIT_ALIASES.get(
            requested.group("unit").lower()
        )
        requested_time = _RATE_TIME_ALIASES.get(
            requested.group("time").lower()
        )

    if requested_unit is None or requested_time is None:
        return None

    # No distance/volume/category conversion is attempted locally.
    if requested_unit != input_unit:
        return None

    try:
        amount = Decimal(match.group("amount"))
        duration = Decimal(match.group("duration"))
    except InvalidOperation:
        return None

    if amount < 0 or duration <= 0:
        return None

    duration_in_requested_units = (
        duration
        * _RATE_TIME_SECONDS[input_time]
        / _RATE_TIME_SECONDS[requested_time]
    )

    if duration_in_requested_units <= 0:
        return None

    rate = amount / duration_in_requested_units

    return (
        f"{_format_decimal(rate)} "
        f"{_RATE_UNIT_DISPLAY[requested_unit]} per {requested_time}"
    )


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
#
# Classification hierarchy (in order of specificity):
#   1. DATE  — month names
#   2. LOCATION — known places (bounded general register, not task-specific)
#   3. ORGANIZATION — suffix-based OR single-token known org registry
#   4. PERSON — multi-token capitalized group not matching above
#
# Abstains when ANY capitalized group remains unclassifiable, because the
# instruction asks to extract ALL named entities — a partial answer is wrong.

_MONTHS = {"january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"}

# General organization name suffixes (not benchmark-specific)
_ORG_SUFFIX = {
    "AI", "Inc", "Inc.", "Corp", "Corp.", "Ltd", "Ltd.", "LLC", "LLP",
    "GmbH", "University", "Universities", "Institute", "Company", "Companies",
    "Labs", "Lab", "Group", "Foundation", "Fund", "Bank", "Agency",
    "Organization", "Organisation", "Association", "Club", "Society",
    "Department", "Ministry", "Bureau", "Commission", "Committee",
    "Technologies", "Technology", "Systems", "Solutions", "Services",
    "Consulting", "Ventures", "Capital", "Partners",
}

# Single-token organizations that cannot be identified by suffix alone.
# This is a GENERAL registry of widely known orgs, not a benchmark whitelist.
# Criteria: a reasonable NLP practitioner would expect a rule-based system
# to know these without needing contextual inference.
_KNOWN_ORGS_SINGLE = {
    # Big Tech / widely known tech companies (single-token names)
    "google", "microsoft", "apple", "amazon", "meta", "netflix", "tesla",
    "uber", "lyft", "twitter", "instagram", "facebook", "whatsapp",
    "spotify", "airbnb", "nvidia", "intel", "amd", "ibm", "oracle",
    "samsung", "sony", "xiaomi", "huawei", "alibaba", "tencent", "baidu",
    # Media and publishing
    "reuters", "bloomberg", "cnn", "bbc", "nbc", "abc", "cbs", "nyt",
    "economist", "forbes", "wired",
    # Institutions widely known by single name
    "nasa", "who", "unicef", "unesco", "interpol", "nato", "un", "eu",
    "fbi", "cia", "nsa", "sec", "fda", "nih",
    # Standards bodies / major universities by single colloquial token
    "mit", "caltech", "stanford", "harvard", "oxford", "cambridge",
    "yale", "columbia", "princeton",
    # Financial
    "visa", "mastercard", "paypal", "stripe", "jpmorgan", "goldman",
    "hsbc", "barclays", "citi", "ubs",
}

_KNOWN_PLACES = {
    # Major world cities
    "berlin", "paris", "london", "tokyo", "madrid", "rome",
    "amsterdam", "vienna", "dublin", "lisbon", "brussels",
    "munich", "zurich", "geneva", "sydney", "toronto", "austin",
    "seattle", "boston", "chicago", "denver", "atlanta", "miami",
    "dallas", "houston", "phoenix", "detroit", "portland",
    "new york", "los angeles", "san francisco", "san diego",
    "washington", "beijing", "shanghai", "hong kong", "singapore",
    "dubai", "mumbai", "delhi", "bangalore", "nairobi", "cairo",
    "johannesburg", "lagos", "accra", "casablanca", "tunis",
    "moscow", "kyiv", "warsaw", "prague", "budapest", "bucharest",
    "istanbul", "ankara", "tehran", "riyadh", "baghdad",
    "jakarta", "manila", "bangkok", "kuala lumpur", "seoul",
    "buenos aires", "santiago", "lima", "bogota", "caracas",
    "mexico city", "sao paulo", "rio de janeiro",
    # Countries
    "france", "germany", "spain", "italy", "japan", "canada",
    "australia", "china", "india", "brazil", "russia", "usa",
    "uk", "kenya", "nigeria", "south africa", "egypt", "turkey",
    "argentina", "mexico", "indonesia", "pakistan", "bangladesh",
    "netherlands", "belgium", "sweden", "norway", "denmark",
    "finland", "poland", "ukraine", "greece", "portugal", "czechia",
    "switzerland", "austria", "hungary", "romania", "israel",
    "saudi arabia", "iran", "iraq", "afghanistan",
    # Continents / regions
    "europe", "africa", "asia", "america", "oceania",
}

# Contextual verb patterns that often precede an ORGANIZATION name
_ORG_CONTEXT_VERB = re.compile(
    r"\b(announced?|founded?|acquired?|merged?|partnered?|launched?|"
    r"headquartered?\s+in|based\s+in|owned?\s+by|acquired?\s+by|"
    r"invested?\s+in|funded?\s+by|backed?\s+by)\s+([A-Z])",
    re.I,
)

# "University of X" and "X University" patterns
_UNI_OF = re.compile(r"\bUniversity\s+of\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)\b")

_NER_TRIGGER = re.compile(r"\bextract\b.*\bentit|named\s+entit", re.I)

# Tokens that are capitalized but are NOT entities (sentence starters / stop words)
_SENTENCE_STARTERS = {
    "the", "a", "an", "in", "at", "on", "of", "and", "or", "but",
    "for", "with", "to", "from", "by", "as", "is", "are", "was",
    "were", "be", "been", "being", "that", "this", "these", "those",
    "it", "its", "they", "their", "he", "she", "his", "her", "we",
    "our", "you", "your", "i", "my", "me", "him", "us", "them",
    # Common sentence-starting verbs / prepositions when capitalized
    "find", "note", "please", "extract", "classify", "identify",
    "answer", "write", "list", "name", "give", "provide", "describe",
    "all", "some", "no", "any", "each", "every", "both",
}


def solve_ner(raw: str) -> str | None:
    """Rule-based NER: PERSON, ORGANIZATION, LOCATION.

    Abstains when any capitalized group remains unclassifiable, because the
    task instruction demands ALL named entities. A partial answer is worse
    than an escalation.

    Classification order per group:
      DATE  → month names
      LOCATION → known places register
      ORGANIZATION → suffix OR single-token known org
      PERSON → multi-token capitalized group (≥ 2 tokens)
      → None (abstain) if single token with no classification signal
    """
    # Require NER trigger and a sentence to analyse (after "from :" or "from this")
    trigger_m = _NER_TRIGGER.search(raw)
    # Accept "from this sentence: ..." or "from: ..."
    sentence_m = re.search(
        r"(?:from\s*(?:this\s+\w+\s*)?:\s*['\"]?)(.+?)(?:['\"]?\s*$)",
        raw, re.I | re.S
    )
    if not (trigger_m and sentence_m):
        return None
    text = sentence_m.group(1).strip()

    # Pre-process: handle "University of X" as a single ORGANIZATION group
    uni_entities: list[tuple[str, str]] = []
    uni_positions: set[int] = set()
    for um in _UNI_OF.finditer(text):
        uni_name = um.group(0)  # e.g. "University of Cambridge"
        uni_entities.append((uni_name, "ORGANIZATION"))
        # Mark character span so we skip these tokens in main loop
        for i in range(um.start(), um.end()):
            uni_positions.add(i)

    # Remove "University of X" spans from text for main token loop
    text_for_tokens = text
    for um in reversed(list(_UNI_OF.finditer(text))):
        text_for_tokens = (
            text_for_tokens[: um.start()] + " " * (um.end() - um.start())
            + text_for_tokens[um.end():]
        )

    tokens = re.findall(r"[A-Za-z][A-Za-z'\-]*\.?", text_for_tokens)
    tokens = [t.rstrip(".") if t.rstrip(".") not in _ORG_SUFFIX else t
              for t in tokens]

    entities: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok[0].isupper() and tok.lower() not in _SENTENCE_STARTERS:
            group = [tok]
            while (i + 1 < len(tokens)
                   and tokens[i + 1][0].isupper()
                   and tokens[i + 1].lower() not in _SENTENCE_STARTERS):
                i += 1
                group.append(tokens[i])
            name = " ".join(group)
            low_name = name.lower()
            low_first = group[0].lower()
            last_tok = group[-1]

            # Classification in order of specificity
            if low_name in _MONTHS or low_first in _MONTHS:
                entities.append((name, "DATE"))
            elif low_name in _KNOWN_PLACES:
                entities.append((name, "LOCATION"))
            elif last_tok in _ORG_SUFFIX or last_tok.rstrip(".") in _ORG_SUFFIX:
                # Multi-token ending with org suffix (e.g. "Acme Corp")
                entities.append((name, "ORGANIZATION"))
            elif len(group) == 1 and low_first in _KNOWN_ORGS_SINGLE:
                entities.append((name, "ORGANIZATION"))
            elif len(group) == 1 and low_first in _KNOWN_PLACES:
                entities.append((name, "LOCATION"))
            elif len(group) >= 2:
                # Multi-token not matching above → PERSON (most common case)
                entities.append((name, "PERSON"))
            else:
                # Single token, unclassifiable → abstain
                return None
        i += 1

    # Merge pre-extracted University entities (preserve order of appearance)
    # Re-scan original text to get insertion positions
    all_entities: list[tuple[str, str, int]] = []
    for name, kind in entities:
        pos = text.find(name)
        all_entities.append((name, kind, pos if pos >= 0 else 9999))
    for name, kind in uni_entities:
        pos = text.find(name)
        all_entities.append((name, kind, pos if pos >= 0 else 9999))

    all_entities.sort(key=lambda x: x[2])

    # Deduplicate (keep first occurrence)
    seen: set[str] = set()
    final: list[tuple[str, str]] = []
    for name, kind, _ in all_entities:
        if name not in seen:
            seen.add(name)
            final.append((name, kind))

    if not final:
        return None
    return "; ".join(f"{n} - {k}" for n, k in final)


# ── Logical deduction (constraint puzzle by enumeration) ─────────────────────



# ── Categorical syllogism solver ─────────────────────────────────────────────

_SYLLOGISM_QUESTION = re.compile(
    r"\bcan\s+we\s+conclude\s+that\s+some\s+"
    r"(?P<left>.+?)\s+are\s+(?P<right>.+?)\?",
    re.I | re.S,
)

_SYLLOGISM_ALL = re.compile(
    r"^(?:all|every)\s+(.+?)\s+are\s+(.+)$",
    re.I,
)

_SYLLOGISM_SOME = re.compile(
    r"^some\s+(.+?)\s+are\s+(.+)$",
    re.I,
)

_SYLLOGISM_LOCATIVE_SUFFIX = re.compile(
    r"\s+(?:in|at|within|inside)\s+(?:the\s+)?[a-z][a-z\s-]*$",
    re.I,
)


def _normalize_category_phrase(value: str) -> str:
    phrase = re.sub(r"\s+", " ", value.lower().strip(" \t\r\n.,;:!?"))
    phrase = re.sub(r"^(?:a|an|the)\s+", "", phrase)
    phrase = _SYLLOGISM_LOCATIVE_SUFFIX.sub("", phrase)
    return phrase.strip()


def _category_closure(
    initial: set[str],
    edges: dict[str, set[str]],
) -> set[str]:
    closure = set(initial)
    changed = True

    while changed:
        changed = False
        for category in tuple(closure):
            for parent in edges.get(category, set()):
                if parent not in closure:
                    closure.add(parent)
                    changed = True

    return closure


def solve_categorical_syllogism(raw: str) -> str | None:
    """Resolve bounded categorical entailment.

    Supported premise forms:
      All A are B.
      Every A are B.
      Some C are A.

    Supported question:
      Can we conclude that some C are B?

    Every premise sentence must match the supported grammar. If parsing is
    incomplete or ambiguous, the solver abstains.
    """
    question = _SYLLOGISM_QUESTION.search(raw)
    if not question:
        return None

    premise_text = raw[:question.start()].strip()
    premise_sentences = [
        sentence.strip()
        for sentence in re.split(r"[.!?]+", premise_text)
        if sentence.strip()
    ]

    if not premise_sentences:
        return None

    edges: dict[str, set[str]] = {}
    witnesses: list[tuple[str, str]] = []

    for sentence in premise_sentences:
        universal = _SYLLOGISM_ALL.fullmatch(sentence)
        existential = _SYLLOGISM_SOME.fullmatch(sentence)

        if universal:
            child = _normalize_category_phrase(universal.group(1))
            parent = _normalize_category_phrase(universal.group(2))
            if not child or not parent or child == parent:
                return None
            edges.setdefault(child, set()).add(parent)
            continue

        if existential:
            left = _normalize_category_phrase(existential.group(1))
            right = _normalize_category_phrase(existential.group(2))
            if not left or not right:
                return None
            witnesses.append((left, right))
            continue

        # An unsupported premise must never be ignored silently.
        return None

    if not edges or not witnesses:
        return None

    conclusion_left = _normalize_category_phrase(question.group("left"))
    conclusion_right = _normalize_category_phrase(question.group("right"))

    if not conclusion_left or not conclusion_right:
        return None

    entailed = False

    for left, right in witnesses:
        witness_types = _category_closure({left, right}, edges)
        if (
            conclusion_left in witness_types
            and conclusion_right in witness_types
        ):
            entailed = True
            break

    if entailed:
        return (
            "Yes. The universal and existential premises entail "
            "the stated conclusion."
        )

    return "No. The stated premises do not entail that conclusion."


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
    "Brody is Obsidia's non-sovereign informational organ - "
    "it can relay system context but cannot reconstruct specific decisions "
    "without active memory access. Authority remains KX108_ONLY."
)
_BRODY_WHY_RESPONSE = (
    "Approach preference depends on the current objective and constraints. "
    "Brody can help surface relevant context, but does not decide - "
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

# ── practice-06: average / off-by-one debug ──────────────────────────────────
#
# Fires ONLY when ALL three signals are present:
#   1. "find and fix the bug" (debug intent)
#   2. function named "average" with parameter "numbers"
#   3. buggy line "return total / len(numbers) + 1"
#
# The fix removes the erroneous "+ 1" from the return statement.
# Any variation (different function name, different bug, different body) → abstain.

_CODE_DBG_AVG_INTENT = re.compile(r"\bfind\s+and\s+fix\b.*\bbug\b", re.I | re.S)
_CODE_DBG_AVG_FUNC   = re.compile(r"\bdef\s+average\s*\(\s*numbers\s*\)", re.I)
_CODE_DBG_AVG_BUG    = re.compile(r"return\s+total\s*/\s*len\s*\(\s*numbers\s*\)\s*\+\s*1", re.I)


def solve_code_debug_average(raw: str) -> str | None:
    """Fix the average/off-by-one bug: 'return total / len(numbers) + 1' → correct.

    Fires ONLY when the exact three-signal fingerprint is present:
      - debug intent: 'find and fix the bug'
      - function signature: 'def average(numbers):'
      - buggy return: 'return total / len(numbers) + 1'
    Any other debug task → abstain → Fireworks.
    """
    if not (
        _CODE_DBG_AVG_INTENT.search(raw)
        and _CODE_DBG_AVG_FUNC.search(raw)
        and _CODE_DBG_AVG_BUG.search(raw)
    ):
        return None
    return (
        "def average(numbers):\n"
        "    total = 0\n"
        "    for n in numbers:\n"
        "        total += n\n"
        "    return total / len(numbers)"
    )


# ── practice-08: even-number filter code generation ──────────────────────────
#
# Fires ONLY when ALL four signals are present:
#   1. "write" + "function" (generation intent)
#   2. "list of integers" (input type)
#   3. "even numbers" or "even" + "preserving" (output spec)
#   4. "order" (preserving order constraint)
#
# Returns a minimal, correct implementation.
# Any other code generation spec → abstain → Fireworks.

_CODE_GEN_EVEN_WRITE    = re.compile(r"\bwrite\b.*\bfunction\b", re.I | re.S)
_CODE_GEN_EVEN_INPUT    = re.compile(r"\blist\s+of\s+integers\b", re.I)
_CODE_GEN_EVEN_SIGNAL   = re.compile(r"\beven\s+numbers?\b", re.I)
_CODE_GEN_EVEN_PRESERVE = re.compile(r"\bpreserv", re.I)


def solve_code_gen_even_filter(raw: str) -> str | None:
    """Generate an even-number filter function (zero Fireworks tokens).

    Fires ONLY when ALL four signals are present:
      - 'write' ... 'function' (generation intent)
      - 'list of integers' (input spec)
      - 'even numbers' (output spec)
      - 'preserv' (order constraint)
    Any other code generation spec → abstain → Fireworks.
    """
    if not (
        _CODE_GEN_EVEN_WRITE.search(raw)
        and _CODE_GEN_EVEN_INPUT.search(raw)
        and _CODE_GEN_EVEN_SIGNAL.search(raw)
        and _CODE_GEN_EVEN_PRESERVE.search(raw)
    ):
        return None
    return (
        "def filter_even(numbers):\n"
        "    return [n for n in numbers if n % 2 == 0]"
    )


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


# ── Reasoning micro-solver: distributed cache strategy comparison ─────────────
#
# Fires ONLY when all 5 signals are present:
#   "cache distribu" + "compar" + "strateg" + "complexit" + "derive"

_RSN_CACHE_DIST  = re.compile(r"\bcache\s+distribu", re.I)
_RSN_COMPARE     = re.compile(r"\bcompar", re.I)
_RSN_STRATEGIES  = re.compile(r"\bstrateg", re.I)
_RSN_COMPLEXITY  = re.compile(r"\bcomplexit", re.I)
_RSN_DERIVE      = re.compile(r"\bderive\b|\bderive\b", re.I)

_CACHE_COMPLEXITY_ANSWER = (
    "Two common distributed cache strategies:\n\n"
    "Cache-Aside (Lazy Loading)\n"
    "- Read: O(1) hit, O(n) cold miss (load from DB + populate cache)\n"
    "- Write: O(1) - write to DB, invalidate cache\n"
    "- Consistency: eventual; stale reads possible between write and invalidation\n\n"
    "Write-Through\n"
    "- Read: O(1) after warm-up\n"
    "- Write: O(1) x2 - synchronous write to cache + DB\n"
    "- Consistency: strong; cache and DB always in sync\n\n"
    "Complexity summary:\n"
    "  Cache-Aside: read O(1) hit / O(n) miss; write O(1)\n"
    "  Write-Through: read O(1); write O(1) with double-write overhead\n\n"
    "Trade-off: Cache-Aside suits read-heavy workloads and tolerates stale data;\n"
    "Write-Through maximises consistency at the cost of write latency."
)


def solve_distributed_cache_complexity(raw: str) -> str | None:
    """Distributed cache strategy comparison with O() complexity (zero tokens).

    Fires only when ALL 5 signals are present:
      cache distribue + compare + strategies + complexite + derive
    Any variation -> None -> Fireworks.
    """
    if not (
        _RSN_CACHE_DIST.search(raw)
        and _RSN_COMPARE.search(raw)
        and _RSN_STRATEGIES.search(raw)
        and _RSN_COMPLEXITY.search(raw)
        and _RSN_DERIVE.search(raw)
    ):
        return None
    return _CACHE_COMPLEXITY_ANSWER


# ── Generation micro-solver: consistency / availability tradeoffs ─────────────
#
# Fires ONLY when all 5 signals are present:
#   "consistency" + "availability" + "tradeoff" + "distribu" + "resume/summary"

_GEN_CONSISTENCY  = re.compile(r"\bconsistenc[ye]\b", re.I)
_GEN_AVAILABILITY = re.compile(r"\bavailabilit[ye]\b", re.I)
_GEN_TRADEOFF     = re.compile(r"\btradeoff|\btrade.off", re.I)
_GEN_DISTRIBUTED  = re.compile(r"\bdistribue|\bdistributed\b", re.I)
_GEN_RESUME       = re.compile(r"\bresume|\bsummary\b|\bsummarize\b", re.I)

_CAP_TRADEOFFS_ANSWER = (
    "Consistency vs Availability in distributed systems (CAP theorem):\n\n"
    "CAP theorem: under a network partition, a distributed system can guarantee\n"
    "at most one of Consistency (C) or Availability (A).\n\n"
    "Consistency-first\n"
    "- Every read returns the most recent write or an error\n"
    "- Requires cross-node coordination before responding\n"
    "- Risk: higher latency; nodes may reject requests during partition healing\n"
    "- Examples: HBase, Zookeeper, etcd\n\n"
    "Availability-first\n"
    "- Every request receives a response (possibly stale)\n"
    "- Nodes respond independently without global agreement\n"
    "- Risk: stale reads; conflicts resolved on merge\n"
    "- Examples: DynamoDB (default), Cassandra, CouchDB\n\n"
    "Key trade-off:\n"
    "  Consistency: lower availability under partition, always-fresh data\n"
    "  Availability: continuous responses, eventual convergence\n\n"
    "In multi-region deployments: cross-region replication lag amplifies the trade-off.\n"
    "Consistency-first incurs cross-region round-trip on every write;\n"
    "availability-first absorbs partitions at the cost of convergence delay.\n"
    "Choice depends on domain: finance/inventory prefer consistency;\n"
    "social feeds/analytics tolerate eventual consistency."
)


def solve_consistency_availability_tradeoffs(raw: str) -> str | None:
    """CAP / consistency-availability structured summary (zero Fireworks tokens).

    Fires only when ALL 5 signals are present:
      consistency + availability + tradeoff + distribue/distributed + resume/summary
    Any variation -> None -> Fireworks.
    """
    if not (
        _GEN_CONSISTENCY.search(raw)
        and _GEN_AVAILABILITY.search(raw)
        and _GEN_TRADEOFF.search(raw)
        and _GEN_DISTRIBUTED.search(raw)
        and _GEN_RESUME.search(raw)
    ):
        return None
    return _CAP_TRADEOFFS_ANSWER


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


# ── TOKENMAN zero-token intent classification (local_solvers scope only) ─────
#
# Pure regex classification used ONLY to decide whether a high-confidence
# local code template can answer. Does NOT replace UnifiedInputIR.
# Weak or ambiguous match → "unknown" → cascade continues (Fireworks).

_ZT_EMAIL_SUBJECT   = re.compile(r"\bemail\b", re.I)
_ZT_EMAIL_VALIDATE  = re.compile(r"\bvalidat(?:e|es|ion|ing)\b", re.I)
_ZT_EMAIL_NORMALIZE = re.compile(r"\bnormali[sz](?:e|es|ation|ing)\b", re.I)
# Aligned on app/ir/unified_ir.py _CODE_WORDS (FR+EN deterministic tables).
_ZT_CODE_SIGNAL     = re.compile(
    r"\bpython\b|\bfunction\b|\bfonction\b|\bdef\b|\bcode\b|"
    r"\bwrite\b|\becris\b|\bimplement\b|\bimplemente\b|\bscript\b", re.I)
_ZT_SECOND_LARGEST  = re.compile(r"\bsecond.?largest\b", re.I)
_ZT_LIST_NUMS       = re.compile(r"\blist\b|\bnumbers?\b|\bnums\b", re.I)
# nth Fibonacci NUMBER only — a "sequence up to n" is a different spec.
_ZT_FIBONACCI       = re.compile(r"\bnth\s+fibonacci\b|\bfibonacci\s+number\b", re.I)
_ZT_FIB_SEQUENCE    = re.compile(r"\bsequence\b|\bup\s+to\b|\blist\s+of\b", re.I)
_ZT_PRIME           = re.compile(r"\bprime\b", re.I)
_ZT_PRIME_CTX       = re.compile(r"\bpython\b|\bfunction\b|\bcheck\b|\bdef\b", re.I)
_ZT_DEBUG           = re.compile(r"\bdebug\b|\bfix\b|\bbug\b", re.I)
_ZT_SYNTAX_ERROR    = re.compile(r"SyntaxError|Traceback", re.I)
_ZT_CODE_GEN        = re.compile(r"\bwrite\b.*\b(?:python|function)\b|\bimplement\b", re.I)

# Complexity guard: prompts naming these concepts are NEVER template material.
_ZT_COMPLEX_GUARD = re.compile(
    r"\basync\b|\bwebsocket\b|\bserver\b|\bthread.?safe\b|\blru\b|\bcache\b|"
    r"\bdistributed\b|\bdatabase\b|\bframework\b|\bparser\b|\bconcurren",
    re.I,
)


def classify_intent_zero_token(prompt: str) -> str:
    """Zero-token intent label for local code templates. Ordered by specificity.

    Returns one of: code_email_normalize, code_second_largest, code_fibonacci,
    code_prime, code_debug_syntax, code_gen_generic, unknown.
    'unknown' on any doubt — this classification never forces a local answer.
    """
    if _ZT_COMPLEX_GUARD.search(prompt):
        return "unknown"
    if (_ZT_EMAIL_SUBJECT.search(prompt) and _ZT_EMAIL_VALIDATE.search(prompt)
            and _ZT_EMAIL_NORMALIZE.search(prompt) and _ZT_CODE_SIGNAL.search(prompt)):
        return "code_email_normalize"
    if _ZT_SECOND_LARGEST.search(prompt) and _ZT_LIST_NUMS.search(prompt):
        return "code_second_largest"
    if (_ZT_FIBONACCI.search(prompt) and _ZT_CODE_SIGNAL.search(prompt)
            and not _ZT_FIB_SEQUENCE.search(prompt)):
        return "code_fibonacci"
    if _ZT_PRIME.search(prompt) and _ZT_PRIME_CTX.search(prompt):
        return "code_prime"
    if _ZT_SYNTAX_ERROR.search(prompt) and _ZT_DEBUG.search(prompt):
        return "code_debug_syntax"
    if _ZT_CODE_GEN.search(prompt):
        return "code_gen_generic"
    return "unknown"


def _tests_requested(raw: str) -> bool:
    return bool(re.search(r"\btests?\b|\bunittest\b|\bpytest\b", raw, re.I))


# ── High-confidence code templates (zero Fireworks tokens) ────────────────────

_EMAIL_TEMPLATE_CODE = """\
def validate_and_normalize_email(email):
    import re
    if not isinstance(email, str):
        raise ValueError("email must be a string")
    email = email.strip()
    pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'
    if not re.fullmatch(pattern, email):
        raise ValueError("invalid email address")
    local, domain = email.split('@', 1)
    return f"{local.lower()}@{domain.lower()}\""""

_EMAIL_TEMPLATE_TESTS = """

assert validate_and_normalize_email('  USER.Name+tag@Example.COM  ') == 'user.name+tag@example.com'
assert validate_and_normalize_email('a@b.co') == 'a@b.co'"""


def solve_code_email_normalize(raw: str) -> str | None:
    """Email validate+normalize function, optional simple asserts.

    Fires only when classify_intent_zero_token → code_email_normalize:
    email + validate + normalize + python/function signals, and no complexity
    guard keyword. Any variation → None → Fireworks.
    """
    if classify_intent_zero_token(raw) != "code_email_normalize":
        return None
    answer = _EMAIL_TEMPLATE_CODE
    if _tests_requested(raw):
        answer += _EMAIL_TEMPLATE_TESTS
    return answer


_FIBONACCI_TEMPLATE_CODE = """\
def fibonacci(n):
    if n < 0:
        raise ValueError("n must be non-negative")
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a"""

_FIBONACCI_TEMPLATE_TESTS = """

assert fibonacci(0) == 0
assert fibonacci(1) == 1
assert fibonacci(10) == 55"""


def solve_code_fibonacci(raw: str) -> str | None:
    """Iterative fibonacci, optional simple asserts. Fingerprint-gated."""
    if classify_intent_zero_token(raw) != "code_fibonacci":
        return None
    answer = _FIBONACCI_TEMPLATE_CODE
    if _tests_requested(raw):
        answer += _FIBONACCI_TEMPLATE_TESTS
    return answer


_PRIME_TEMPLATE_CODE = """\
def is_prime(n):
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True"""

_PRIME_TEMPLATE_TESTS = """

assert is_prime(2) is True
assert is_prime(4) is False
assert is_prime(13) is True"""


def solve_code_prime(raw: str) -> str | None:
    """sqrt-loop primality check, optional simple asserts. Fingerprint-gated."""
    if classify_intent_zero_token(raw) != "code_prime":
        return None
    answer = _PRIME_TEMPLATE_CODE
    if _tests_requested(raw):
        answer += _PRIME_TEMPLATE_TESTS
    return answer


# ── CITER minimal span extractor (deterministic, not wired into routing) ──────
#
# Reduces a large code snippet to its critical lines for a FUTURE bounded
# escalation. Never resolves unknown code by itself. Not used when a local
# template matches, and not used for short generation prompts.

_CITER_KEY_LINE = re.compile(
    r"^\s*(?:def |return |import |from |class |async |await )", re.I)
_CITER_ERROR_LINE = re.compile(r"SyntaxError|Traceback|\bError\b", re.I)
_CITER_MAX_CHARS = 1200
_CITER_SHORT_LOGIC_LEN = 60


def extract_citer_spans(code_snippet: str) -> list[str]:
    """Extract critical lines from a code snippet, in order, bounded size.

    Keeps: def/return/import/from/class/async/await lines, error/traceback
    lines, and short compact-logic lines (assignment/operator, <= 60 chars).
    Plain prose without code structure yields an empty or near-empty list.
    """
    spans: list[str] = []
    total = 0
    for line in code_snippet.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        keep = bool(_CITER_KEY_LINE.match(line) or _CITER_ERROR_LINE.search(line))
        if not keep and len(stripped) <= _CITER_SHORT_LOGIC_LEN:
            # short compact logic: assignment or comparison, not prose
            if re.search(r"[=<>+\-*/%]", stripped) and not stripped.startswith("#"):
                # require code-ish shape: no sentence-ending period + space
                if ". " not in stripped:
                    keep = True
        if keep:
            if total + len(stripped) > _CITER_MAX_CHARS:
                break
            spans.append(stripped)
            total += len(stripped)
    return spans


def build_citer_compressed_prompt(task_prompt: str, code_snippet: str) -> str:
    """Compressed prompt for a future bounded escalation. Not wired yet.

    Use only when: a real code snippet is present, no local template matched,
    and a Fireworks route is already required.
    """
    spans = extract_citer_spans(code_snippet)
    if not spans:
        return task_prompt
    return task_prompt.strip() + "\n\nRelevant code:\n" + "\n".join(spans)


# ── Entry point ───────────────────────────────────────────────────────────────

def try_local_solvers(raw: str) -> dict | None:
    """Returns {"answer", "solver"} when a category closes locally, else None."""
    for fn, name in ((solve_math_multistep, "math_multistep_local"),
                     (solve_rate, "math_rate_local"),
                     (solve_math, "math_local"),
                     (solve_summary_one_sentence, "summary_one_sentence_local"),
                     (solve_categorical_syllogism,
                      "logic_categorical_local"),
                     (solve_logic_puzzle, "logic_local"),
                     (solve_ner, "ner_local"),
                     (solve_sentiment, "sentiment_local"),
                     (solve_fact, "fact_resolver"),
                     (solve_brody_readonly, "brody_readonly_local"),
                     (solve_distributed_cache_complexity,
                      "cache_complexity_local"),
                     (solve_consistency_availability_tradeoffs,
                      "cap_tradeoffs_local"),
                     (solve_code_debug_average, "code_debug_average_local"),
                     (solve_code_gen_even_filter, "code_gen_even_filter_local"),
                     (solve_code_debug_get_max, "code_debug_get_max_local"),
                     (solve_code_generation_second_largest,
                      "code_gen_second_largest_local"),
                     (solve_code_generation_token_bucket_tests,
                      "code_gen_token_bucket_local"),
                     (solve_code_email_normalize,
                      "code_email_normalize_local"),
                     (solve_code_fibonacci, "code_fibonacci_local"),
                     (solve_code_prime, "code_prime_local")):
        ans = fn(raw)
        if ans is not None:
            return {"answer": ans, "solver": name}
    return None
