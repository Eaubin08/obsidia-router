"""Local category solvers — deterministic answers, zero remote tokens."""
from __future__ import annotations

import re

from app.router.decision import decide
from app.router.local_solvers import (
    solve_math, solve_math_multistep, solve_sentiment,
    solve_summary_one_sentence, try_local_solvers,
)


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
    a = solve_sentiment("Classify the sentiment: 'I loved this movie, it was excellent'")
    assert a and a.startswith("positive")

def test_sentiment_negative():
    a = solve_sentiment("What is the sentiment of: 'terrible service, worst experience'")
    assert a and a.startswith("negative")

def test_sentiment_negation():
    a = solve_sentiment("Classify the sentiment: 'this is not good at all'")
    assert a and a.startswith("negative")

def test_sentiment_mixed_explicit():
    # practice-03 : contraste explicite + signal positif + signal negatif
    # -> "mixed" deterministe (zero token local)
    result = solve_sentiment(
        "Classify the sentiment of this review: "
        "The battery life is great, but the screen scratches too easily."
    )
    assert result is not None and result.startswith("mixed")

def test_sentiment_abstains_contrast_single_polarity():
    # contraste present mais un seul signal -> escalade necessaire
    assert solve_sentiment(
        "Classify the sentiment: 'The design is beautiful, but I am unsure.'") is None

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
    assert d["solver_answer"].startswith("positive")

def test_frame_still_wins_over_solver():
    # Une action monde reste HOLD meme si elle contient un pattern math.
    d = decide("push 15% of 80 to production")
    assert d["route"] == "hold_commands_only"

def test_non_solver_requests_unaffected():
    assert decide("status")["route"] == "no_model_needed"
    # Short brody-contextual prompts now close via brody_readonly_local.
    # Verify that longer / technical prompts still escalate.
    assert try_local_solvers(
        "analyse et compare le contexte de cache distribue et derive la complexite"
    ) is None


# ── Summary one-sentence (extractive local compressor) ───────────────────────

_PRACTICE_04 = (
    "Summarize the following in exactly one sentence: The Obsidia router "
    "compiles every request into a structured intent, checks deterministic "
    "gates, and only escalates to a remote model when local structure "
    "cannot answer, which reduces token spend substantially."
)

def test_summary_one_sentence_practice_04():
    result = solve_summary_one_sentence(_PRACTICE_04)
    assert result is not None
    # Must be a complete sentence
    assert result.endswith(".")
    # Must contain the main subject (Obsidia router)
    assert re.search(r"obsidia", result, re.I)
    # Must have stripped the relative clause
    assert "which reduces" not in result

def test_summary_one_sentence_abstains_no_trigger():
    assert solve_summary_one_sentence("The Obsidia router is great.") is None

def test_summary_one_sentence_abstains_source_too_short():
    assert solve_summary_one_sentence("Summarize in one sentence: hi there.") is None

def test_summary_one_sentence_abstains_no_one_sentence():
    # Missing "one sentence" → abstain
    assert solve_summary_one_sentence(
        "Summarize the following: The Obsidia router compiles requests.") is None

def test_decide_routes_summarisation_locally():
    d = decide(_PRACTICE_04)
    assert d["route"] == "local_solver"
    assert d["model"] is None  # zero remote token
    assert re.search(r"obsidia", d["solver_answer"], re.I)

def test_frame_wins_over_summary():
    d = decide("push: summarize the system in one sentence: The router is great and works well.")
    assert d["route"] == "hold_commands_only"


# ── NER + Logic V1 ────────────────────────────────────────────────────────────

def test_ner_practice_05():
    from app.router.local_solvers import solve_ner
    a = solve_ner("Extract all named entities and their types from: "
                  "Maria Sanchez joined Fireworks AI in Berlin last March.")
    assert a == ("Maria Sanchez - PERSON; Fireworks AI - ORGANIZATION; "
                 "Berlin - LOCATION; March - DATE")

def test_ner_abstains_on_unknown_entity():
    from app.router.local_solvers import solve_ner
    assert solve_ner("Extract entities from: Xylophorus visited Qbrtz.") is None

def test_logic_practice_07():
    from app.router.local_solvers import solve_logic_puzzle
    a = solve_logic_puzzle("Three friends, Sam, Jo, and Lee, each own a "
                           "different pet: cat, dog, bird. Sam does not own "
                           "the bird. Jo owns the dog. Who owns the cat?")
    assert a == "Sam owns the cat."

def test_logic_abstains_without_unique_solution():
    from app.router.local_solvers import solve_logic_puzzle
    assert solve_logic_puzzle("Sam, Jo and Lee own pets. Who owns the cat?") is None
    assert solve_logic_puzzle("Three friends, Sam, Jo, and Lee, each own a "
                              "different pet: cat, dog, bird. Who owns the cat?") is None


# ── Math multistep ────────────────────────────────────────────────────────────

def test_math_multistep_practice_02():
    result = solve_math_multistep(
        "A store has 240 items. It sells 15% on Monday and 60 more on Tuesday. "
        "How many items remain?"
    )
    assert result == "144"

def test_math_multistep_abstains_no_remain_question():
    assert solve_math_multistep(
        "A store has 240 items. It sells 15% on Monday and 60 more on Tuesday."
    ) is None

def test_math_multistep_abstains_multiple_percents():
    assert solve_math_multistep(
        "A store has 100 items. It sells 10% then 20% and 5 more. "
        "How many items remain?"
    ) is None

def test_math_multistep_abstains_negative_result():
    assert solve_math_multistep(
        "A store has 10 items. It sells 90% and 50 more. "
        "How many items remain?"
    ) is None

def test_math_multistep_does_not_interfere_with_simple_math():
    # solve_math_multistep ne doit pas repondre a un calcul simple
    assert solve_math_multistep("What is 15% of 80") is None
    assert solve_math_multistep("calculate 12 * 4") is None

def test_decide_routes_math_multistep_locally():
    d = decide(
        "A store has 240 items. It sells 15% on Monday and 60 more on Tuesday. "
        "How many items remain?"
    )
    assert d["route"] == "local_solver"
    assert d["solver_answer"] == "144"
    assert d["model"] is None

def test_frame_wins_over_math_multistep():
    d = decide(
        "push: a store has 240 items, sells 15% then 60 more, how many remain?"
    )
    assert d["route"] == "hold_commands_only"


# ── Fact resolver (canonical boot knowledge) ──────────────────────────────────

def test_fact_resolver_practice_01_capital_and_water():
    from app.router.fact_resolver import solve_fact
    result = solve_fact(
        "What is the capital of Australia, and what body of water is it near?"
    )
    assert result is not None
    import re
    assert re.search(r"canberra", result, re.I)
    assert re.search(r"burley\s*griffin", result, re.I)

def test_fact_resolver_capital_only():
    from app.router.fact_resolver import solve_fact
    result = solve_fact("What is the capital of Australia?")
    assert result is not None
    assert "Canberra" in result

def test_fact_resolver_abstains_unknown_country():
    from app.router.fact_resolver import solve_fact
    assert solve_fact("What is the capital of Zylophoria?") is None

def test_fact_resolver_abstains_no_capital_trigger():
    from app.router.fact_resolver import solve_fact
    assert solve_fact("What lake is in Australia?") is None

def test_fact_resolver_abstains_no_question_trigger():
    from app.router.fact_resolver import solve_fact
    assert solve_fact("The capital of Australia is Canberra.") is None

def test_decide_routes_factual_locally():
    d = decide(
        "What is the capital of Australia, and what body of water is it near?"
    )
    assert d["route"] == "local_solver"
    assert d["model"] is None
    import re
    assert re.search(r"canberra", d["solver_answer"], re.I)
    assert re.search(r"burley\s*griffin", d["solver_answer"], re.I)

def test_frame_wins_over_fact_resolver():
    d = decide("push: what is the capital of Australia?")
    assert d["route"] == "hold_commands_only"
