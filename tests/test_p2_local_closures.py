"""P2 local closures: generic rate and categorical syllogism."""

from app.router.local_solvers import (
    solve_categorical_syllogism,
    solve_rate,
    try_local_solvers,
)
from benchmarks.model_selection_matrix import grade_answer


PRACTICE_02 = (
    "A train travels 180 kilometers in 2.5 hours. "
    "What is its average speed in kilometers per hour?"
)

PRACTICE_07 = (
    "All roses in the garden are red. "
    "Some flowers in the garden are roses. "
    "Can we conclude that some flowers in the garden are red? "
    "Answer yes or no and explain briefly."
)


# ── Rate positives ────────────────────────────────────────────────────────────

def test_rate_practice_02():
    answer = solve_rate(PRACTICE_02)
    assert answer == "72 kilometers per hour"
    assert grade_answer("practice-02", answer)["pass"]


def test_rate_factory_units_per_hour():
    answer = solve_rate(
        "A factory produces 120 units in 2 hours. "
        "What is the rate in units per hour?"
    )
    assert answer == "60 units per hour"


def test_rate_liters_per_minute():
    answer = solve_rate(
        "A pump moves 300 liters over 5 minutes. "
        "What is the flow in liters per minute?"
    )
    assert answer == "60 liters per minute"


def test_rate_requests_per_second():
    answer = solve_rate(
        "A service processes 900 requests in 30 seconds. "
        "What is the throughput in requests per second?"
    )
    assert answer == "30 requests per second"


def test_rate_converts_minutes_to_hour():
    answer = solve_rate(
        "A cyclist travels 30 kilometers in 90 minutes. "
        "What is the average speed in kilometers per hour?"
    )
    assert answer == "20 kilometers per hour"


# ── Rate abstentions ──────────────────────────────────────────────────────────

def test_rate_abstains_on_zero_duration():
    assert solve_rate(
        "A machine produces 10 units in 0 hours. "
        "What is the rate in units per hour?"
    ) is None


def test_rate_abstains_on_incompatible_requested_unit():
    assert solve_rate(
        "A train travels 100 kilometers in 2 hours. "
        "What is the average speed in miles per hour?"
    ) is None


def test_rate_abstains_without_rate_intent():
    assert solve_rate(
        "A train travels 100 kilometers in 2 hours."
    ) is None


def test_rate_abstains_on_multiple_measurements():
    assert solve_rate(
        "A machine produces 10 units in 2 hours and "
        "produces 20 units in 3 hours. What is the rate per hour?"
    ) is None


# ── Syllogism positives / negatives ──────────────────────────────────────────

def test_syllogism_practice_07():
    answer = solve_categorical_syllogism(PRACTICE_07)
    assert answer is not None
    assert answer.lower().startswith("yes")
    assert grade_answer("practice-07", answer)["pass"]


def test_syllogism_generic_positive():
    answer = solve_categorical_syllogism(
        "All engineers are professionals. "
        "Some employees are engineers. "
        "Can we conclude that some employees are professionals?"
    )
    assert answer is not None
    assert answer.lower().startswith("yes")


def test_syllogism_transitive_positive():
    answer = solve_categorical_syllogism(
        "All sparrows are birds. "
        "All birds are animals. "
        "Some garden visitors are sparrows. "
        "Can we conclude that some garden visitors are animals?"
    )
    assert answer is not None
    assert answer.lower().startswith("yes")


def test_syllogism_recognized_non_entailment():
    answer = solve_categorical_syllogism(
        "All cats are mammals. "
        "Some pets are dogs. "
        "Can we conclude that some pets are mammals?"
    )
    assert answer is not None
    assert answer.lower().startswith("no")


# ── Syllogism abstentions ─────────────────────────────────────────────────────

def test_syllogism_abstains_on_unsupported_premise():
    assert solve_categorical_syllogism(
        "Most roses are red. "
        "Some flowers are roses. "
        "Can we conclude that some flowers are red?"
    ) is None


def test_syllogism_abstains_without_existential_premise():
    assert solve_categorical_syllogism(
        "All roses are red. "
        "Can we conclude that some roses are red?"
    ) is None


def test_syllogism_abstains_on_unrelated_logic_puzzle():
    assert solve_categorical_syllogism(
        "Three friends each own a different pet. Who owns the cat?"
    ) is None


# ── Canonical cascade ─────────────────────────────────────────────────────────

def test_rate_is_wired_into_canonical_cascade():
    result = try_local_solvers(PRACTICE_02)
    assert result is not None
    assert result["solver"] == "math_rate_local"
    assert result["answer"] == "72 kilometers per hour"


def test_syllogism_is_wired_into_canonical_cascade():
    result = try_local_solvers(PRACTICE_07)
    assert result is not None
    assert result["solver"] == "logic_categorical_local"
    assert result["answer"].lower().startswith("yes")
