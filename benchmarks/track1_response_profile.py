"""Track 1 response profile — Brody-like sizing policy, zero private imports.

Classifies expected answer size BEFORE the Fireworks call, and observed
answer size AFTER. Inspired by brody_adaptive_response_policy word-count
tiers (55 / 180 / 380) but fully self-contained — no dependency on
apps/obsidia_api or any X-108 private stack.

Profiles
--------
  SHORT            max_tokens=160   reasoning / analysis tasks
  MEDIUM           max_tokens=220   generation / summary tasks
  CODE             max_tokens=320   code generation tasks
  BOUNDARY_COMPACT max_tokens=120   boundary / governance decision tasks

Word-count observation tiers (Brody-like):
  <= 55  words  → SHORT
  <= 180 words  → MEDIUM
  <= 380 words  → DEEP
  >  380 words  → LONG
"""
from __future__ import annotations

# ── Tier constants (mirror brody_adaptive_response_policy thresholds) ─────────

_TIER_SHORT: int = 55
_TIER_MEDIUM: int = 180
_TIER_DEEP: int = 380

# ── Per-profile max_tokens budgets ────────────────────────────────────────────

_MAX_TOKENS: dict[str, int] = {
    "SHORT": 160,
    "MEDIUM": 220,
    "CODE": 320,
    "BOUNDARY_COMPACT": 120,
}

# ── Per-profile system prompts for Track 1 official mode ─────────────────────
#
# Each profile gets a targeted instruction that suppresses the specific
# preamble patterns observed in live runs:
#   SHORT/MEDIUM: "The user asks...", "Analyze the Request...", reasoning chains
#   CODE:         "Analyze the Request...", planning sections, markdown fences

_SYSTEM_PROMPT_CODE: str = (
    "Return only the requested file content. "
    "No analysis. No explanation. No planning. "
    "Do not describe the task. "
    "Do not use markdown fences unless explicitly requested. "
    "Output valid code only."
)

_SYSTEM_PROMPT_SHORT_MEDIUM: str = (
    "Answer the request directly. "
    "Do not describe what the user asked. "
    "Do not start with 'The user asks'. "
    "Do not include analysis steps, planning, or preamble. "
    "Answer in the same language as the user. "
    "Avoid tables unless explicitly requested."
)

_SYSTEM_PROMPT_BOUNDARY: str = (
    "State the decision concisely. No preamble. No explanation."
)

_SYSTEM_PROMPTS: dict[str, str] = {
    "SHORT":            _SYSTEM_PROMPT_SHORT_MEDIUM,
    "MEDIUM":           _SYSTEM_PROMPT_SHORT_MEDIUM,
    "CODE":             _SYSTEM_PROMPT_CODE,
    "BOUNDARY_COMPACT": _SYSTEM_PROMPT_BOUNDARY,
}

# Public alias kept for backward compatibility with tests that import it directly
TRACK1_SYSTEM_PROMPT: str = _SYSTEM_PROMPT_SHORT_MEDIUM

# ── Keyword signals ───────────────────────────────────────────────────────────

_CODE_REQUEST_SIGNALS: frozenset[str] = frozenset({
    "implemente", "implement", "fonction", "function", "def ",
    "class ", "script", "programme", "program",
})

_ID_CODE_TOKENS: frozenset[str] = frozenset({
    "code", "implement", "function", "script",
})

_ID_GENERATION_TOKENS: frozenset[str] = frozenset({
    "generation", "summary", "resume", "generate", "summarize",
})

_ID_REASONING_TOKENS: frozenset[str] = frozenset({
    "reasoning", "analysis", "compare", "analyse", "reason",
})


# ── Internal helpers ──────────────────────────────────────────────────────────

def _count_words(text: str) -> int:
    return len(text.split()) if text else 0


def _id_contains(task_id: str, tokens: frozenset[str]) -> bool:
    low = task_id.lower()
    return any(t in low for t in tokens)


# ── Public API ────────────────────────────────────────────────────────────────

def classify_expected_profile(
    task_id: str,
    request: str,
    route: str,
    intent_type: str | None = None,
    target_layer: str | None = None,
) -> str:
    """Return one of SHORT / MEDIUM / CODE / BOUNDARY_COMPACT.

    Operates BEFORE generation — no answer text available.
    Uses task_id sub-tokens, request keywords, and route.
    """
    # Governance / boundary routes always stay compact
    if route in ("hold_commands_only", "denied", "clarification_needed"):
        return "BOUNDARY_COMPACT"

    # Non-fireworks non-boundary routes: SHORT is fine (local resolution anyway)
    if route != "fireworks":
        return "SHORT"

    request_lower = request.lower()

    # CODE signals: task_id first (most reliable), then request keywords
    if _id_contains(task_id, _ID_CODE_TOKENS):
        return "CODE"
    if any(sig in request_lower for sig in _CODE_REQUEST_SIGNALS):
        return "CODE"

    # GENERATION / summary signals
    if _id_contains(task_id, _ID_GENERATION_TOKENS):
        return "MEDIUM"

    # REASONING / analysis signals
    if _id_contains(task_id, _ID_REASONING_TOKENS):
        return "SHORT"

    # Fallback: request word-count heuristic
    words = _count_words(request)
    if words <= 20:
        return "SHORT"
    return "MEDIUM"


def classify_observed_answer(answer: str) -> str:
    """Classify the OBSERVED answer text after generation.

    Returns one of SHORT / MEDIUM / DEEP / LONG.
    Uses the same word-count tiers as brody_adaptive_response_policy.
    """
    words = _count_words(answer)
    if words <= _TIER_SHORT:
        return "SHORT"
    if words <= _TIER_MEDIUM:
        return "MEDIUM"
    if words <= _TIER_DEEP:
        return "DEEP"
    return "LONG"


def max_tokens_for_profile(profile: str) -> int:
    """Return the Fireworks max_tokens budget for this profile."""
    return _MAX_TOKENS.get(profile, 220)


def build_track1_system_prompt(profile: str) -> str:
    """Return the per-profile system prompt for Track 1 official calls.

    CODE        → suppresses "Analyze the Request" and planning preambles,
                  forces raw code output.
    SHORT/MEDIUM → suppresses "The user asks..." and reasoning chains,
                  forces direct answer in user's language.
    BOUNDARY_COMPACT → concise decision statement, no preamble.
    """
    return _SYSTEM_PROMPTS.get(profile, _SYSTEM_PROMPT_SHORT_MEDIUM)


def projection_cost(observed_words: int) -> float:
    """Brody-like dissipation cost from answer word count.

    Mirrors the projection_cost logic in brody_thermodynamics_signal:
      > 800 words → 0.50
      > 380 words → 0.30
      < 80  words → 0.10
      else        → 0.00
    """
    if observed_words > 800:
        return 0.50
    if observed_words > _TIER_DEEP:
        return 0.30
    if observed_words < 80:
        return 0.10
    return 0.0


def build_response_profile_telemetry(
    expected_profile: str,
    answer: str,
    bounded_remote_call: bool = False,
) -> dict:
    """Build the telemetry block for receipts_internal.json.

    These fields are NEVER written to results.json (public).
    They mirror the advisory classification that Brody runs post-generation
    via brody_adaptive_response_policy + brody_thermodynamics_signal.

    bounded_remote_call=True signals that this task made a real Fireworks call
    whose output budget was capped BEFORE generation — distinguishing it from
    remote_call_avoided=True tasks where no call was made at all.
    """
    words = _count_words(answer)
    observed = classify_observed_answer(answer)
    if words <= _TIER_SHORT:
        density = "HIGH"
    elif words <= _TIER_MEDIUM:
        density = "NORMAL"
    else:
        density = "LOW"
    return {
        "expected_response_profile": expected_profile,
        "observed_response_size": observed,
        "observed_answer_words": words,
        "density": density,
        "projection_cost": projection_cost(words),
        "compact_policy_source": "brody_like_track1_local",
        "brody_policy_imported": False,
        # A3 audit labels — distinguish bounded remote call from avoided inference
        "bounded_remote_call": bounded_remote_call,
        "response_budget_profile": expected_profile,
        "response_budget_source": "brody_like_track1_local",
        "response_budget_applied_before_generation": bounded_remote_call,
    }
