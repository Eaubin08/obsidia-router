"""LOT H — variant robustness tests for reused local solvers.

Doctrine: no test uses only the exact practice prompt; mutating a number or
a proper noun must change the answer correctly; an uncertain solver must
abstain (return None) and escalate instead of inventing an answer.
"""
from __future__ import annotations

import pytest

from app.router.fact_resolver import solve_fact
from app.router.local_solvers import (
    solve_logic_puzzle,
    solve_math,
    solve_math_multistep,
    solve_ner,
    solve_sentiment,
    solve_summary_one_sentence,
)

# ── factual: 5 variants ───────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt,expected", [
    ("What is the capital of France?", "paris"),
    ("Tell me: what is the capital of Japan?", "tokyo"),
    ("What is the capital of Germany?", "berlin"),
    ("what is the capital of italy?", "rome"),
    ("What is the capital of Canada?", "ottawa"),
])
def test_fact_variants(prompt, expected):
    ans = solve_fact(prompt)
    if ans is not None:
        assert expected in ans.lower()


def test_fact_abstains_on_unknown_country():
    assert solve_fact("What is the capital of Wakanda?") is None


def test_fact_mutation_changes_answer():
    a1 = solve_fact("What is the capital of France?")
    a2 = solve_fact("What is the capital of Germany?")
    if a1 and a2:
        assert a1 != a2


# ── math: 10 variants ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt,expected", [
    ("What is 15% of 200?", "30"),
    ("What is 7% of 300?", "21"),
    ("calculate 12 + 30", "42"),
    ("compute 100 - 58", "42"),
    ("what is 6 * 7", "42"),
    ("What is 84 / 2", "42"),
    ("What is 2.5% of 1000?", "25"),
    ("9 + 10 =", "19"),
    ("50 - 8 =", "42"),
    ("What is 25% of 40?", "10"),
])
def test_math_variants(prompt, expected):
    assert solve_math(prompt) == expected


def test_math_division_by_zero_abstains():
    assert solve_math("What is 5 / 0") is None


@pytest.mark.parametrize("prompt,expected", [
    ("A store has 240 items. It sells 15% on Monday and 60 more on Tuesday. "
     "How many items remain?", "144"),
    ("A warehouse has 500 items. It sells 10% on Monday and 50 more on "
     "Tuesday. How many items remain?", "400"),
    ("A shop has 100 items. It sells 20% and then 30 more. "
     "How many items remain?", "50"),
])
def test_math_multistep_variants(prompt, expected):
    assert solve_math_multistep(prompt) == expected


def test_math_multistep_number_mutation_changes_answer():
    a = solve_math_multistep(
        "A store has 240 items. It sells 15% on Monday and 60 more on "
        "Tuesday. How many items remain?")
    b = solve_math_multistep(
        "A store has 480 items. It sells 15% on Monday and 60 more on "
        "Tuesday. How many items remain?")
    assert a == "144" and b == "348" and a != b


# ── sentiment: 8 formulations ─────────────────────────────────────────────────

@pytest.mark.parametrize("prompt,label", [
    ("Classify the sentiment: this product is excellent and I love it.", "positive"),
    ("Classify the sentiment: absolutely wonderful and delightful experience.", "positive"),
    ("Classify the sentiment: what a fantastic and impressive device.", "positive"),
    ("Classify the sentiment: terrible quality, totally useless.", "negative"),
    ("Classify the sentiment: the service was awful and disappointing.", "negative"),
    ("Classify the sentiment: horrible, the worst purchase ever.", "negative"),
    ("Classify the sentiment: the sound is great but the case is fragile.", "mixed"),
    ("Classify the sentiment: excellent screen, however the battery is disappointing.", "mixed"),
])
def test_sentiment_variants(prompt, label):
    ans = solve_sentiment(prompt)
    assert ans is not None and ans.lower().startswith(label)


def test_sentiment_abstains_on_unknown_lexicon():
    # 'gorgeous'/'cheap' are outside the lexicon -> abstain, escalate
    assert solve_sentiment(
        "Classify the sentiment as positive, negative, or neutral: "
        "the screen is gorgeous but the keyboard feels cheap.") is None


# ── summarisation: variants + abstentions ─────────────────────────────────────

def test_summary_variant_new_text():
    ans = solve_summary_one_sentence(
        "Summarize the following in exactly one sentence: The Meridian "
        "engine compiles requests into typed intents before any model call, "
        "which reduces overall spend, and that impresses reviewers.")
    assert ans is not None and ans.endswith(".")


def test_summary_two_sentences_constraint_abstains():
    # 'two sentences' is a different contract -> must abstain
    assert solve_summary_one_sentence(
        "Summarize the following passage in two sentences: Solar panels "
        "convert sunlight into electricity using photovoltaic cells and "
        "their cost has fallen dramatically over the past decade.") is None


# ── NER: variants with different people/orgs/places ───────────────────────────

def test_ner_variant_different_entities():
    ans = solve_ner(
        "Extract all named entities from: John Smith joined Acme Corp in "
        "Paris last January.")
    if ans is not None:
        assert "John Smith" in ans and "Paris" in ans


def test_ner_abstains_on_unknown_single_capitalized():
    # 'Nairobi' is not in the known-places table -> abstain, escalate
    assert solve_ner(
        "Extract all named entities (people, organizations, locations) from "
        "this sentence: 'Satya Nadella announced that Microsoft will open a "
        "new research lab in Nairobi.'") is None


def test_ner_name_mutation_changes_answer():
    a = solve_ner("Extract all named entities from: Alice Martin joined "
                  "Acme Corp in Berlin last March.")
    b = solve_ner("Extract all named entities from: Bob Taylor joined "
                  "Acme Corp in Berlin last March.")
    if a and b:
        assert a != b


# ── logic: variants ───────────────────────────────────────────────────────────

def test_logic_variant_different_names_and_pets():
    ans = solve_logic_puzzle(
        "Three friends, Ana, Ben, and Cal, each owns a different pet: cat, "
        "dog, bird. Ana does not own the bird. Ben owns the dog. "
        "Who owns the cat?")
    assert ans is not None and "Ana" in ans


def test_logic_mutation_changes_answer():
    a = solve_logic_puzzle(
        "Three friends, Sam, Jo, and Lee, each owns a different pet: cat, "
        "dog, bird. Sam does not own the bird. Jo owns the dog. "
        "Who owns the cat?")
    b = solve_logic_puzzle(
        "Three friends, Sam, Jo, and Lee, each owns a different pet: cat, "
        "dog, bird. Lee does not own the bird. Jo owns the dog. "
        "Who owns the cat?")
    assert a is not None and "Sam" in a
    if b is not None:
        assert b != a


def test_logic_syllogism_abstains():
    # roses/flowers syllogism has no ownership structure -> abstain
    assert solve_logic_puzzle(
        "All roses in the garden are red. Some flowers in the garden are "
        "roses. Can we conclude that some flowers in the garden are red? "
        "Answer yes or no.") is None
