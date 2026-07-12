"""Tests — Track 1 response profile : adaptive response sizing, zero private imports."""
from __future__ import annotations

import pytest

from benchmarks.track1_response_profile import (
    TRACK1_SYSTEM_PROMPT,
    _TIER_DEEP,
    _TIER_MEDIUM,
    _TIER_SHORT,
    build_response_profile_telemetry,
    build_track1_system_prompt,
    classify_expected_profile,
    classify_observed_answer,
    max_tokens_for_profile,
    projection_cost,
)


# ── classify_observed_answer — word-count tiers ───────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("one two three", "SHORT"),
    (" ".join(["word"] * _TIER_SHORT), "SHORT"),
    (" ".join(["word"] * (_TIER_SHORT + 1)), "MEDIUM"),
    (" ".join(["word"] * _TIER_MEDIUM), "MEDIUM"),
    (" ".join(["word"] * (_TIER_MEDIUM + 1)), "DEEP"),
    (" ".join(["word"] * _TIER_DEEP), "DEEP"),
    (" ".join(["word"] * (_TIER_DEEP + 1)), "LONG"),
])
def test_classify_observed_answer_tiers(text, expected):
    assert classify_observed_answer(text) == expected


def test_classify_observed_empty():
    assert classify_observed_answer("") == "SHORT"


# ── classify_expected_profile — fireworks task detection ─────────────────────

def test_fireworks_code_by_task_id():
    assert classify_expected_profile(
        "fireworks_code",
        "implemente une fonction python de rate limiting",
        "fireworks",
    ) == "CODE"


def test_fireworks_generation_by_task_id():
    assert classify_expected_profile(
        "fireworks_generation",
        "genere un resume structure des tradeoffs",
        "fireworks",
    ) == "MEDIUM"


def test_fireworks_reasoning_by_task_id():
    assert classify_expected_profile(
        "fireworks_reasoning",
        "analyse et compare ces deux strategies de cache distribue",
        "fireworks",
    ) == "SHORT"


def test_code_detected_by_request_keyword():
    assert classify_expected_profile(
        "task_xyz",
        "write a fonction python that computes fibonacci",
        "fireworks",
    ) == "CODE"


def test_code_detected_by_implemente_keyword():
    assert classify_expected_profile(
        "bench_01",
        "implemente une classe LRU avec tests",
        "fireworks",
    ) == "CODE"


def test_generation_short_request_falls_back_to_medium():
    # A generic fireworks task with moderate request length → MEDIUM
    result = classify_expected_profile(
        "fw_summary",
        "genere un texte court sur les avantages du consensus raft dans un cluster",
        "fireworks",
    )
    assert result in ("SHORT", "MEDIUM")


def test_non_fireworks_route_short():
    assert classify_expected_profile(
        "status_simple", "statut du systeme", "no_model_needed"
    ) == "SHORT"


def test_hold_route_boundary_compact():
    assert classify_expected_profile(
        "risky_push", "push tout sur main", "hold_commands_only"
    ) == "BOUNDARY_COMPACT"


def test_denied_route_boundary_compact():
    assert classify_expected_profile(
        "destructive", "rm -rf tout", "denied"
    ) == "BOUNDARY_COMPACT"


def test_clarification_route_boundary_compact():
    assert classify_expected_profile(
        "ambiguous", "fais le truc", "clarification_needed"
    ) == "BOUNDARY_COMPACT"


# ── max_tokens_for_profile — budget par profil ────────────────────────────────

def test_max_tokens_short_is_lower_than_medium():
    assert max_tokens_for_profile("SHORT") < max_tokens_for_profile("MEDIUM")


def test_max_tokens_code_higher_than_medium():
    assert max_tokens_for_profile("CODE") > max_tokens_for_profile("MEDIUM")


def test_max_tokens_boundary_compact_lowest():
    bc = max_tokens_for_profile("BOUNDARY_COMPACT")
    assert bc <= max_tokens_for_profile("SHORT")
    assert bc <= max_tokens_for_profile("MEDIUM")
    assert bc <= max_tokens_for_profile("CODE")


def test_max_tokens_unknown_profile_returns_default():
    # Unknown profile should not raise and return a sane default
    result = max_tokens_for_profile("UNKNOWN_PROFILE")
    assert isinstance(result, int)
    assert result > 0


def test_max_tokens_all_profiles():
    assert max_tokens_for_profile("SHORT") == 160
    assert max_tokens_for_profile("MEDIUM") == 220
    assert max_tokens_for_profile("CODE") == 320
    assert max_tokens_for_profile("BOUNDARY_COMPACT") == 120


# ── build_track1_system_prompt ────────────────────────────────────────────────

def test_system_prompt_short_no_user_asks():
    """SHORT prompt doit interdire 'The user asks' (pattern observé en live)."""
    sp = build_track1_system_prompt("SHORT")
    assert "Do not start with" in sp or "The user asks" in sp
    assert "directly" in sp.lower()


def test_system_prompt_medium_no_tables():
    sp = build_track1_system_prompt("MEDIUM")
    assert "table" in sp.lower()


def test_system_prompt_code_no_analysis():
    """CODE prompt doit interdire l'analyse et forcer du code brut."""
    sp = build_track1_system_prompt("CODE")
    assert "No analysis" in sp
    assert "Output valid code" in sp or "code only" in sp.lower()


def test_system_prompt_code_no_planning():
    sp = build_track1_system_prompt("CODE")
    assert "No planning" in sp


def test_system_prompt_code_different_from_short():
    """CODE et SHORT doivent avoir des prompts distincts."""
    assert build_track1_system_prompt("CODE") != build_track1_system_prompt("SHORT")


def test_system_prompt_short_same_as_medium():
    """SHORT et MEDIUM partagent le même prompt (pattern de preamble identique)."""
    assert build_track1_system_prompt("SHORT") == build_track1_system_prompt("MEDIUM")


def test_system_prompt_unknown_profile_returns_default():
    """Un profil inconnu retourne le prompt SHORT/MEDIUM par défaut."""
    sp = build_track1_system_prompt("UNKNOWN")
    assert "directly" in sp.lower()


def test_system_prompt_track1_constant_is_short_medium():
    """TRACK1_SYSTEM_PROMPT reste exporté comme alias du prompt SHORT/MEDIUM."""
    assert TRACK1_SYSTEM_PROMPT == build_track1_system_prompt("SHORT")


# ── projection_cost ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("words, expected", [
    (10, 0.10),    # < 80 words
    (80, 0.0),     # exactly 80
    (200, 0.0),    # within normal range
    (381, 0.30),   # > TIER_DEEP
    (801, 0.50),   # > 800
])
def test_projection_cost_thresholds(words, expected):
    assert projection_cost(words) == expected


# ── build_response_profile_telemetry ─────────────────────────────────────────

def test_telemetry_has_all_required_fields():
    tel = build_response_profile_telemetry("CODE", "def foo(): return 42")
    required = {
        "expected_response_profile",
        "observed_response_size",
        "observed_answer_words",
        "density",
        "projection_cost",
        "compact_policy_source",
        "brody_policy_imported",
        # A3 audit labels
        "bounded_remote_call",
        "response_budget_profile",
        "response_budget_source",
        "response_budget_applied_before_generation",
    }
    assert required <= set(tel.keys())


def test_telemetry_brody_not_imported():
    tel = build_response_profile_telemetry("SHORT", "yes")
    assert tel["brody_policy_imported"] is False


def test_telemetry_compact_policy_source():
    tel = build_response_profile_telemetry("MEDIUM", "some answer")
    assert tel["compact_policy_source"] == "brody_like_track1_local"


def test_telemetry_expected_profile_preserved():
    tel = build_response_profile_telemetry("CODE", "print('hello')")
    assert tel["expected_response_profile"] == "CODE"


def test_telemetry_short_answer_high_density():
    short_answer = "yes no ok"
    tel = build_response_profile_telemetry("SHORT", short_answer)
    assert tel["observed_response_size"] == "SHORT"
    assert tel["density"] == "HIGH"


def test_telemetry_long_answer_low_density():
    long_answer = " ".join(["word"] * 400)
    tel = build_response_profile_telemetry("MEDIUM", long_answer)
    assert tel["observed_response_size"] == "LONG"
    assert tel["density"] == "LOW"


def test_telemetry_word_count_accurate():
    answer = "one two three four five"
    tel = build_response_profile_telemetry("SHORT", answer)
    assert tel["observed_answer_words"] == 5


# ── A3 audit labels ───────────────────────────────────────────────────────────

def test_a3_bounded_remote_call_default_false():
    """bounded_remote_call defaults to False — non-Fireworks tasks are not bounded."""
    tel = build_response_profile_telemetry("SHORT", "yes")
    assert tel["bounded_remote_call"] is False
    assert tel["response_budget_applied_before_generation"] is False


def test_a3_bounded_remote_call_true_when_fireworks():
    """bounded_remote_call=True when a Fireworks call was budget-capped."""
    tel = build_response_profile_telemetry("MEDIUM", "some answer", bounded_remote_call=True)
    assert tel["bounded_remote_call"] is True
    assert tel["response_budget_applied_before_generation"] is True


def test_a3_response_budget_profile_matches_expected():
    tel = build_response_profile_telemetry("CODE", "def foo(): pass", bounded_remote_call=True)
    assert tel["response_budget_profile"] == "CODE"


def test_a3_response_budget_source():
    tel = build_response_profile_telemetry("SHORT", "ok", bounded_remote_call=False)
    assert tel["response_budget_source"] == "brody_like_track1_local"


def test_a3_boundary_compact_not_bounded_remote():
    """BOUNDARY_COMPACT routes (hold/deny/clarify) are never remote calls."""
    tel = build_response_profile_telemetry("BOUNDARY_COMPACT", "DENIED: ...",
                                           bounded_remote_call=False)
    assert tel["bounded_remote_call"] is False
    assert tel["response_budget_applied_before_generation"] is False
    assert tel["response_budget_profile"] == "BOUNDARY_COMPACT"


def test_a3_all_four_fields_present():
    """The four A3 audit fields must always be present."""
    for profile in ("SHORT", "MEDIUM", "CODE", "BOUNDARY_COMPACT"):
        tel = build_response_profile_telemetry(profile, "test")
        for field in ("bounded_remote_call", "response_budget_profile",
                      "response_budget_source", "response_budget_applied_before_generation"):
            assert field in tel, f"A3 field missing: {field} for profile {profile}"
