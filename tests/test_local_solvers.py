"""Local category solvers — deterministic answers, zero remote tokens."""
from __future__ import annotations

from app.router.decision import decide
from app.router.local_solvers import solve_math, solve_sentiment, try_local_solvers


# ── Math ──────────────────────────────────────────────────────────────────────

def test_math_arithmetic():
    assert solve_math("What is 12 * 4") == "48"
    assert solve_math("calculate 100 / 8") == "12.5"
    assert solve_math("7 + 35") == "42"

def test_math_percentage():
    assert solve_math("What is 15% of 80") == "12"
    assert solve_math("compute 12.5% of 200") == "25"

def test_math_refuses_ambiguous():
    assert solve_math("explain how multiplication works") is None
    assert solve_math("what is 5 / 0") is None
    assert solve_math("solve this equation system with matrices") is None


# ── Sentiment ─────────────────────────────────────────────────────────────────

def test_sentiment_positive():
    assert solve_sentiment(
        "Classify the sentiment: 'I loved this movie, it was excellent'") == "positive"

def test_sentiment_negative():
    assert solve_sentiment(
        "What is the sentiment of: 'terrible service, worst experience'") == "negative"

def test_sentiment_negation():
    assert solve_sentiment(
        "Classify the sentiment: 'this is not good at all'") == "negative"

def test_sentiment_refuses_without_trigger():
    # Pas de mot-cle 'sentiment/classify' : ne pas repondre a l'aveugle.
    assert solve_sentiment("I loved this movie") is None

def test_sentiment_refuses_no_signal():
    assert solve_sentiment("Classify the sentiment: 'the sky is blue'") is None


# ── Integration cascade ───────────────────────────────────────────────────────

def test_decide_routes_math_locally():
    d = decide("What is 15% of 80")
    assert d["route"] == "local_solver"
    assert d["solver_answer"] == "12"
    assert d["model"] is None  # zero remote token

def test_decide_routes_sentiment_locally():
    d = decide("Classify the sentiment: 'an amazing, wonderful film'")
    assert d["route"] == "local_solver"
    assert d["solver_answer"] == "positive"

def test_frame_still_wins_over_solver():
    # Une action monde reste HOLD meme si elle contient un pattern math.
    d = decide("push 15% of 80 to production")
    assert d["route"] == "hold_commands_only"

def test_non_solver_requests_unaffected():
    assert decide("status")["route"] == "no_model_needed"
    assert try_local_solvers("explique le contexte de la decision") is None
