"""Track 1 remote answer contract — balanced_compact_v3 (aggressive).

Builds a `remote_answer_contract` dict BEFORE any Fireworks call.
Drives max_tokens, contract prompt, and model selection from request signals
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

# ── Budget table (balanced_compact_v3 — aggressive) ─────────────────────────
#
# quality_discovery_v1 natural completion (gpt-oss-120b, unconstrained):
#   comparison : live 320-token cap exhausted -> quality rollback: 420
#   summary    : 611 tokens  → v3 ceiling: 420
#   code_file  : 1155 tokens → v3 ceiling: 620
#
# Ultra-short contract prompts (≤120 chars) + low ceiling = minimum total cost.
# Accuracy boundary: if quality degrades, roll back per kind by +100.

_BUDGETS: dict[str, int] = {
    "comparison":         420,
    "structured_summary": 420,
    "code_file":          620,
    "direct_answer":      320,
    "clarification":       80,
}

_TARGET_WORDS: dict[str, int] = {
    "comparison":          60,
    "structured_summary":  75,
    "code_file":          130,
    "direct_answer":       60,
    "clarification":       40,
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
    # COMPARISON checked before SUMMARY so that prompts containing both
    # "compare" and "trade-offs" are classified as comparison, not summary.
    if any(sig in low for sig in _COMPARISON_SIGNALS):
        return "comparison"
    if any(sig in low for sig in _DERIVATION_SIGNALS):
        return "comparison"
    if any(sig in low for sig in _SUMMARY_SIGNALS):
        return "structured_summary"
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


def select_model_preference(allowed_models: list[str] | None = None) -> str:
    """Informative default model name for contract metadata/telemetry only.

    LOT C: no environment parsing here — ALLOWED_MODELS parsing is owned
    exclusively by app.adapters.fireworks.allowed_models(); callers that
    have a resolved ladder pass it in explicitly.

    LOT D: this value does NOT select the model actually sent to
    fireworks.chat(). The model that is really called is decided once,
    centrally, by app.router.model_triage.select_model_for_request() inside
    decide(). This field stays for contract telemetry / receipts / back-
    compat only and must never be treated as competing authority.
    """
    if allowed_models:
        return _DEFAULT_MODEL if _DEFAULT_MODEL in allowed_models else allowed_models[0]
    return _DEFAULT_MODEL


# ── Prompt construction ───────────────────────────────────────────────────────
#
# v3 contract prompts are ≤120 chars — no preamble, no meta-reasoning clauses.
# code_only: raw code starting with def, no prose, no fences.

def build_contract_prompt(
    answer_kind: str,
    missing_referent: bool,
    code_only: bool,
    language: str,
    target_words: int,
) -> str:
    # AMD Track 1: answer always in English regardless of request language.
    # LOT H1: summaries need a dedicated final-only contract.
    # The generic "use well-known instances" instruction is invalid for
    # summarisation because it encourages added examples and planning.
    if answer_kind == "structured_summary":
        language_instruction = (
            "Answer in French."
            if language == "fr"
            else "Answer in English."
        )
        return (
            "Final only. Return only the requested summary. "
            "Follow the user's requested sentence count and format "
            "exactly. Do not add examples, a title, markdown, a "
            "preamble, analysis, planning, or commentary. "
            + language_instruction
        )
    lang_instr = "Answer in English."
    if code_only:
        return (
            "Code only. Start with def. "
            "No prose, no markdown, no docstring. "
            "If tests requested, use simple asserts only. No try/except. "
            f"{lang_instr}"
        )
    # No word count injected in prompt — "<= N words" causes the model to emit
    # reasoning steps ("Let's count...", "We need to answer in...").
    # target_words is kept in the contract metadata only.
    # Generic molds only: no hidden-task overfit.
    if answer_kind == "comparison":
        shape_instr = (
            "Final only. Plain labels: A:, B:, Trade-offs:, "
            "Recommendation:. Concise plain text. "
            "No title/table/markdown/preamble/analysis. "
        )
    else:
        shape_instr = ("Final only. Plain text. Keep brief. "
                       "No title/table/markdown/preamble/analysis. ")
    referent_instr = "Use two well-known instances if no examples given. " if missing_referent else ""
    return shape_instr + referent_instr + lang_instr


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

def build_remote_answer_contract(
    request: str, route: str = "fireworks",
    allowed_models: list[str] | None = None,
) -> dict:
    """Build a remote_answer_contract from request signals alone.

    task_id is deliberately absent — it must never drive answer_kind,
    max_tokens, model_preference, or contract_prompt. It may only appear
    in telemetry/receipts added by the caller.

    allowed_models, when passed, only informs the model_preference
    telemetry field (see select_model_preference docstring — LOT C/D). It
    has no effect on max_tokens, contract_prompt, or the model actually
    called.
    """
    language = detect_language(request)
    missing_referent = detect_missing_referent(request)
    answer_kind = classify_answer_kind(request)
    output_shape = classify_output_shape(request, answer_kind)
    ambiguity = classify_ambiguity(request)
    target_words = select_target_words(answer_kind)
    max_tokens = select_max_tokens(answer_kind)
    model_preference = select_model_preference(allowed_models)
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
