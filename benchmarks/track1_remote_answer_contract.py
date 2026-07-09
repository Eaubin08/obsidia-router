"""Track 1 remote answer contract — generic pre-generation cadrage layer.

Builds a `remote_answer_contract` dict BEFORE any Fireworks call.
Drives max_tokens, system prompt, and model selection from request signals
only — never from task_id as decision logic.

Zero private imports. No dependency on Brody/Obsidure/x108.
Calibrated by quality_discovery_v1 with human_margin_high_v0 headroom.
"""
from __future__ import annotations

import re

# ── Model configuration ───────────────────────────────────────────────────────

_DEFAULT_MODEL = "accounts/fireworks/models/gpt-oss-120b"

_EXCLUDED_MODELS: dict[str, str] = {
    "accounts/fireworks/models/glm-5p1": (
        "hardwired meta template / language failure / code_only failure"
    ),
    "accounts/fireworks/models/deepseek-v4-pro": "timeout risk in quality discovery",
    "accounts/fireworks/models/glm-5p2": "code candidate only, not default",
    "accounts/fireworks/models/gemma": "unavailable in current Fireworks catalog",
}

# ── Budget table (human_margin_high_v0) ───────────────────────────────────────
#
# quality_discovery_v1 natural completion (gpt-oss-120b):
#   comparison : 561 tokens  → recommend +15% = 646  → final 850
#   summary    : 611 tokens  → recommend +15% = 703  → final 900
#   code_file  : 1155 tokens → recommend +15% = 1329 → final 1700
#
# Boundary / clarification: compact (no Fireworks call in practice)

_BUDGETS: dict[str, int] = {
    "comparison":         850,
    "structured_summary": 900,
    "code_file":         1700,
    "direct_answer":      850,
    "clarification":      120,
}

_TARGET_WORDS: dict[str, int] = {
    "comparison":         150,
    "structured_summary": 180,
    "code_file":          400,
    "direct_answer":      150,
    "clarification":       60,
}

# ── Language detection ────────────────────────────────────────────────────────

_FR_SIGNALS: frozenset[str] = frozenset({
    "résume", "resume", "résumé", "analyse", "analysez", "analyser",
    "compare", "implemente", "implémente", "fonction", "fichier",
    "ces deux", "ceux-ci", "bref", "concis", "détaillé", "résumer",
    "tradeoffs", "synthèse", "synthese", "système", "systeme",
    "implémentation",
})

_FR_CHAR_RE = re.compile(r"[àâäéèêëîïôùûüçœæ]", re.IGNORECASE)


def detect_language(request: str) -> str:
    if _FR_CHAR_RE.search(request):
        return "fr"
    low = request.lower()
    for sig in _FR_SIGNALS:
        if sig in low:
            return "fr"
    return "en"


# ── Missing referent detection ────────────────────────────────────────────────

_MISSING_REFERENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bces deux\b", re.IGNORECASE),
    re.compile(r"\bthese two\b", re.IGNORECASE),
    re.compile(r"\bci-dessus\b", re.IGNORECASE),
    re.compile(r"\babove\b", re.IGNORECASE),
    re.compile(r"\bfollowing\b", re.IGNORECASE),
    re.compile(r"\bceux-ci\b", re.IGNORECASE),
]


def detect_missing_referent(request: str) -> bool:
    return any(p.search(request) for p in _MISSING_REFERENT_PATTERNS)


# ── Answer kind classification ────────────────────────────────────────────────

_CODE_SIGNALS: frozenset[str] = frozenset({
    "implemente", "implémente", "implement", "fonction", "function",
    "def ", "class ", "script", "programme", "program",
    ".py", "unittest", "pytest",
})

_SUMMARY_SIGNALS: frozenset[str] = frozenset({
    "resume", "résume", "résumé", "summary", "summarize",
    "synthèse", "synthese", "résumer", "tradeoffs", "trade-offs",
    "structured summary", "résumé structuré",
})

_COMPARISON_SIGNALS: frozenset[str] = frozenset({
    "compare", "comparaison", "comparison", "versus", "vs ",
    "analyse et compare", "comparez", "différences", "differences",
})

_DERIVATION_SIGNALS: frozenset[str] = frozenset({
    "dérive", "derive", "complexité", "complexite", "complexity",
    "démontre", "prove", "derive la", "dérive la",
})


def classify_answer_kind(request: str) -> str:
    low = request.lower()
    if any(sig in low for sig in _CODE_SIGNALS):
        return "code_file"
    if any(sig in low for sig in _SUMMARY_SIGNALS):
        return "structured_summary"
    if any(sig in low for sig in _COMPARISON_SIGNALS):
        return "comparison"
    if any(sig in low for sig in _DERIVATION_SIGNALS):
        return "comparison"
    return "direct_answer"


def classify_output_shape(request: str, answer_kind: str) -> str:
    if answer_kind == "code_file":
        return "code_only"
    low = request.lower()
    if "tableau" in low or ("table" in low and "tradeoffs" not in low):
        return "table_sections"
    return "compact_sections"


def classify_ambiguity(request: str) -> str:
    words = len(request.split())
    if words <= 4:
        return "high"
    if words <= 10:
        return "medium"
    low = request.lower()
    if any(w in low for w in ("ceux-ci", "ci-dessus", "these two", "ces deux", "above")):
        return "low"
    return "none"


# ── Parameter selection ───────────────────────────────────────────────────────

def select_target_words(answer_kind: str) -> int:
    return _TARGET_WORDS.get(answer_kind, 150)


def select_max_tokens(answer_kind: str) -> int:
    return _BUDGETS.get(answer_kind, 850)


def select_model_preference() -> str:
    """Regle AMD : ne jamais appeler un modele hors ALLOWED_MODELS (publie
    au launch day, injecte par le harness). Le defaut calibre n'est utilise
    que s'il figure dans la liste ; sinon premier modele autorise."""
    import os
    allowed = [m.strip() for m in os.environ.get("ALLOWED_MODELS", "").split(",")
               if m.strip()]
    if allowed:
        return _DEFAULT_MODEL if _DEFAULT_MODEL in allowed else allowed[0]
    return _DEFAULT_MODEL


# ── Prompt construction ───────────────────────────────────────────────────────
#
# Rules derived from quality_discovery_v1 live observations:
#   - Never use "canonical examples"        → gpt-oss quoted the instruction verbatim
#   - Never use "The instruction says"      → causes meta-reasoning in body
#   - Never "The user asks" / "Analyze the Request" / "Understand the Goal"
#   - No planning, no reasoning chains, no preamble
#   - code_only: raw code, no explanation, no fences unless requested

def build_contract_prompt(
    answer_kind: str,
    missing_referent: bool,
    code_only: bool,
    language: str,
    target_words: int,
) -> str:
    # AMD Track 1 rule: every answer must be in English, regardless of the
    # request language. The detected language stays available as telemetry.
    lang_instr = "Answer in English."
    base = (
        "Answer the request directly and concisely. "
        "Do not start with 'The user asks', 'The user wants', 'Understand the Goal', "
        "'Analyze the Request', or any description of the request. "
        "Do not include analysis steps, reasoning chains, planning, or preamble. "
        "Go straight to the answer. "
    )
    if code_only:
        return (
            base
            + "Return only valid code. "
            "No explanation before or after the code. "
            "No markdown code fences unless the request explicitly asks for them. "
            f"{lang_instr} "
            "Avoid tables unless explicitly requested."
        )
    shape_instr = ""
    if answer_kind in ("comparison", "structured_summary", "direct_answer"):
        shape_instr = (
            f"Structure the answer in at most 2-3 compact sections. "
            f"Target {target_words} words total. "
        )
    referent_instr = ""
    if missing_referent:
        referent_instr = (
            "If no specific examples are given, use two common well-known instances "
            "and answer directly without mentioning that examples were missing. "
        )
    return (
        base
        + shape_instr
        + referent_instr
        + f"{lang_instr} "
        + "Avoid tables unless explicitly requested."
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _collect_risk_flags(
    answer_kind: str,
    missing_referent: bool,
    ambiguity: str,
) -> list[str]:
    flags: list[str] = []
    if answer_kind == "code_file":
        flags.append("truncation_risk_code")
    if missing_referent:
        flags.append("missing_referent")
    if ambiguity in ("medium", "high"):
        flags.append(f"ambiguity_{ambiguity}")
    return flags


def _collect_source_signals(
    request: str,
    answer_kind: str,
    missing_referent: bool,
    language: str,
) -> list[str]:
    signals = [f"language_{language}"]
    low = request.lower()
    if answer_kind == "code_file":
        signals.append("code_request")
        if any(t in low for t in ("test", "tests", "unittest", "pytest")):
            signals.append("tests_requested")
    if answer_kind == "structured_summary":
        signals.append("structured_summary_request")
    if answer_kind == "comparison":
        signals.append("comparison_request")
        if any(sig in low for sig in _DERIVATION_SIGNALS):
            signals.append("derivation_request")
    if missing_referent:
        signals.append("missing_referent_detected")
    if "tableau" in low or ("table" in low and "tradeoffs" not in low):
        signals.append("table_explicit_request")
    if any(w in low for w in ("bref", "concis", "court", "brief", "short", "concise")):
        signals.append("brevity_requested")
    if any(w in low for w in ("détaillé", "detailed", "complet", "complete", "exhaustif")):
        signals.append("detail_requested")
    return signals


# ── Public API ────────────────────────────────────────────────────────────────

def build_remote_answer_contract(request: str, route: str = "fireworks") -> dict:
    """Build a remote_answer_contract from request signals alone.

    task_id is deliberately absent — it must never drive answer_kind,
    max_tokens, model_preference, or contract_prompt. It may only appear
    in telemetry/receipts added by the caller.
    """
    language = detect_language(request)
    missing_referent = detect_missing_referent(request)
    answer_kind = classify_answer_kind(request)
    output_shape = classify_output_shape(request, answer_kind)
    ambiguity = classify_ambiguity(request)
    target_words = select_target_words(answer_kind)
    max_tokens = select_max_tokens(answer_kind)
    model_preference = select_model_preference()
    code_only = answer_kind == "code_file"
    contract_prompt = build_contract_prompt(
        answer_kind, missing_referent, code_only, language, target_words
    )
    risk_flags = _collect_risk_flags(answer_kind, missing_referent, ambiguity)
    source_signals = _collect_source_signals(request, answer_kind, missing_referent, language)

    return {
        "contract_version":          "track1_remote_answer_contract_v0",
        "language":                  language,
        "answer_kind":               answer_kind,
        "output_shape":              output_shape,
        "missing_referent":          missing_referent,
        "ambiguity_level":           ambiguity,
        "target_words":              target_words,
        "max_tokens":                max_tokens,
        "model_preference":          model_preference,
        "forbid_meta_reasoning":     True,
        "forbid_task_description":   True,
        "forbid_planning":           True,
        "forbid_unrequested_tables": True,
        "code_only":                 code_only,
        "contract_prompt":           contract_prompt,
        "risk_flags":                risk_flags,
        "source_signals":            source_signals,
        "private_policy_imported":   False,
        "model_matrix_calibrated":   True,
        "calibration_source":        "quality_discovery_v1",
        "budget_headroom_policy":    "human_margin_high_v0",
    }
