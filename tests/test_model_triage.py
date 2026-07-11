"""LOT D — ordered adaptive model triage.

app.router.model_triage.select_model_for_request() is the single authority
for "which model" once a Fireworks escalation is already justified. No
network calls anywhere in this file.
"""
from __future__ import annotations

import pytest

from app.router.decision import decide
from app.router.model_triage import (
    RUNG_LARGE,
    RUNG_MEDIUM,
    RUNG_SMALL,
    select_model_for_request,
    select_rung,
)

SMALL = "small-model"
MEDIUM = "medium-model"
LARGE_120B = "gpt-oss-120b"


# ── select_rung — signal classification ───────────────────────────────────────

def test_short_direct_question_is_rung_small():
    assert select_rung("What is the capital of France?") == RUNG_SMALL


def test_short_comparison_is_rung_small():
    assert select_rung("Compare A and B briefly.") == RUNG_SMALL


def test_long_non_code_prompt_is_rung_medium():
    long_prompt = "Explain this in depth. " * 30  # > 400 chars
    assert len(long_prompt) > 400
    assert select_rung(long_prompt) == RUNG_MEDIUM


def test_simple_code_request_is_rung_medium():
    assert select_rung("Implement a function that reverses a string.") == RUNG_MEDIUM


def test_code_answer_kind_forces_medium_even_without_keyword():
    # answer_kind="code_file" overrides keyword absence
    assert select_rung("do the thing with the widget", answer_kind="code_file") == RUNG_MEDIUM


def test_complex_code_request_is_rung_large():
    assert select_rung(
        "Implement a complex distributed cache with concurrency control."
    ) == RUNG_LARGE


def test_long_code_request_is_rung_large():
    long_code = "implement " + "a module " * 60 + "in core.py"
    assert len(long_code) > 400
    assert select_rung(long_code) == RUNG_LARGE


# ── select_model_for_request — ladder mechanics ───────────────────────────────

def test_select_model_for_request_empty_ladder_raises():
    with pytest.raises(ValueError):
        select_model_for_request("hello", [])


def test_select_model_for_request_single_model_ladder_never_errors():
    result = select_model_for_request(
        "Implement a complex distributed cache with concurrency control.",
        [SMALL],
    )
    assert result["selected_model"] == SMALL
    assert result["selected_rung"] == 0


def test_select_model_for_request_preserves_order_not_names():
    # index 0 wins for a short/simple request regardless of what the
    # model is named — order supplied by the caller is the sole authority
    result = select_model_for_request("hi", [LARGE_120B, SMALL])
    assert result["selected_model"] == LARGE_120B
    assert result["selected_rung"] == 0


def test_select_model_for_request_returns_trace_fields():
    result = select_model_for_request("hi", [SMALL, MEDIUM, LARGE_120B])
    assert set(result) == {"selected_model", "selected_rung", "selection_reason"}
    assert isinstance(result["selection_reason"], str) and result["selection_reason"]


# ── Simulations A / B / C / D (static, no network) ────────────────────────────
#
# Exercised directly against select_model_for_request(), matching the five
# request categories from the LOT D spec (direct question, comparison, code
# simple, code complex, long prompt) via their answer_kind signal — the same
# signal the escalation blocks in run_official.py / run_benchmark.py pass in.
# decide()'s own IR-driven routing (reasoning/code_request -> fireworks vs
# question -> brody) is a separate, untouched concern, checked below only
# for parity, not for these five categories.

_DIRECT_SHORT = ("What year did this happen?", "direct_answer")
_COMPARISON_SHORT = ("Compare A and B.", "comparison")
_CODE_SIMPLE = ("Write a function that reverses a list.", "code_file")
_CODE_COMPLEX = ("Implement a complex distributed cache with concurrency control.", "code_file")
_LONG_PROMPT = ("Please explain this topic in great detail. " * 20, "direct_answer")


def _model_for(ladder, case):
    request, answer_kind = case
    return select_model_for_request(request, ladder, answer_kind=answer_kind)["selected_model"]


def test_simulation_a_small_medium_120b():
    ladder = [SMALL, MEDIUM, LARGE_120B]
    assert _model_for(ladder, _DIRECT_SHORT) == SMALL
    assert _model_for(ladder, _COMPARISON_SHORT) == SMALL
    assert _model_for(ladder, _CODE_SIMPLE) == SMALL
    assert _model_for(ladder, _CODE_COMPLEX) == LARGE_120B
    assert _model_for(ladder, _LONG_PROMPT) == MEDIUM


def test_simulation_b_120b_first_order_is_authority():
    ladder = [LARGE_120B, SMALL]
    # rung 0 -> index 0 -> 120b; rung 1+ clamped to the last index -> small
    assert _model_for(ladder, _DIRECT_SHORT) == LARGE_120B
    assert _model_for(ladder, _CODE_SIMPLE) == LARGE_120B
    assert _model_for(ladder, _CODE_COMPLEX) == SMALL


def test_simulation_c_single_model_ladder():
    ladder = [SMALL]
    for case in (_DIRECT_SHORT, _COMPARISON_SHORT, _CODE_SIMPLE,
                 _CODE_COMPLEX, _LONG_PROMPT):
        assert _model_for(ladder, case) == SMALL


def test_simulation_d_default_ladder_used_when_absent(monkeypatch):
    monkeypatch.delenv("ALLOWED_MODELS", raising=False)
    from app.router.decision import DEFAULT_MODEL_LADDER
    request, _ = _CODE_COMPLEX
    d = decide(request)
    assert d["route"] == "fireworks"
    assert d["model"] in DEFAULT_MODEL_LADDER


# ── Router-level integration: decision["model"] == triage's selected_model ────

def test_decide_model_matches_central_triage_exactly():
    ladder = [SMALL, MEDIUM, LARGE_120B]
    request, _ = _CODE_COMPLEX
    d = decide(request, model_ladder=ladder)
    expected = select_model_for_request(request, ladder, answer_kind="code_file")
    assert d["model"] == expected["selected_model"]
    assert d["selected_rung"] == expected["selected_rung"]
