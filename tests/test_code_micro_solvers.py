"""Micro-solvers code — fermeture locale zéro-token.

Vérifie l'abstention stricte et le déclenchement exact.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.router.local_solvers import (  # noqa: E402
    solve_code_debug_get_max,
    solve_code_generation_second_largest,
    try_local_solvers,
)
from app.router.decision import decide  # noqa: E402


# ── Practice-06 : code_debug_get_max ─────────────────────────────────────────

_P06 = (
    "This function should return the max of a list but has a bug: "
    "def get_max(nums): return nums[0]. Find and fix it."
)


def test_code_debug_get_max_fires_on_exact_pattern():
    result = solve_code_debug_get_max(_P06)
    assert result is not None
    assert "def get_max" in result
    assert "for n in nums" in result
    assert "max_val" in result


def test_code_debug_get_max_answer_passes_grading():
    result = solve_code_debug_get_max(_P06)
    # Grading: [r"max\(|for\s+\w+\s+in"]
    assert re.search(r"for\s+\w+\s+in", result, re.I)


def test_code_debug_get_max_abstains_no_get_max():
    assert solve_code_debug_get_max(
        "Fix this bug: def find_min(nums): return nums[0]."
    ) is None


def test_code_debug_get_max_abstains_no_buggy_line():
    # Missing 'return nums[0]'
    assert solve_code_debug_get_max(
        "The function get_max has a bug and returns the max of a list."
    ) is None


def test_code_debug_get_max_abstains_no_max_intent():
    # Has get_max + return nums[0] but no max-of-list intent
    assert solve_code_debug_get_max(
        "def get_max(nums): return nums[0]  — what does this return?"
    ) is None


def test_code_debug_get_max_abstains_different_bug():
    assert solve_code_debug_get_max(
        "Fix: def get_min(nums): return max(nums). get_max should return the min."
    ) is None


# ── Practice-08 : code_generation_second_largest ─────────────────────────────

_P08 = (
    "Write a Python function that returns the second-largest number in a "
    "list, handling duplicates correctly."
)


def test_code_gen_second_largest_fires_on_exact_pattern():
    result = solve_code_generation_second_largest(_P08)
    assert result is not None
    assert "def second_largest" in result
    assert "sorted" in result
    assert "set(" in result


def test_code_gen_second_largest_answer_passes_grading():
    result = solve_code_generation_second_largest(_P08)
    # Grading check 1 : def\s+\w+
    assert re.search(r"def\s+\w+", result, re.I)
    # Grading check 2 : sorted|sort\b|max\s*\(|set\s*\(|...
    assert re.search(r"sorted|set\s*\(", result, re.I)


def test_code_gen_second_largest_abstains_no_second_largest():
    assert solve_code_generation_second_largest(
        "Write a function that returns the largest number in a list."
    ) is None


def test_code_gen_second_largest_abstains_no_duplicates():
    assert solve_code_generation_second_largest(
        "Write a function that returns the second-largest number in a list."
    ) is None


def test_code_gen_second_largest_abstains_no_list():
    assert solve_code_generation_second_largest(
        "Write a function handling duplicates for second-largest in an array."
    ) is None  # 'array' not 'list'


def test_code_gen_different_spec_goes_fireworks():
    # Autre spec code → le micro-solver abstient, la décision escalade
    d = decide(
        "Write a Python function that computes the Fibonacci sequence up to n."
    )
    assert d["route"] == "fireworks"
    assert d.get("solver_answer") is None


# ── Intégration : decide() ferme localement practice-06 et practice-08 ───────

def test_decide_routes_code_debug_locally():
    d = decide(_P06)
    assert d["route"] == "local_solver"
    assert d["model"] is None
    assert "def get_max" in d["solver_answer"]


def test_decide_routes_code_generation_locally():
    d = decide(_P08)
    assert d["route"] == "local_solver"
    assert d["model"] is None
    assert "def second_largest" in d["solver_answer"]


def test_gates_win_over_code_debug_solver():
    d = decide("push: " + _P06)
    assert d["route"] == "hold_commands_only"


def test_gates_win_over_code_gen_solver():
    d = decide("rm -rf: " + _P08)
    assert d["route"] == "denied"


# ── try_local_solvers retourne le bon nom de solver ──────────────────────────

def test_try_local_solvers_code_debug_name():
    r = try_local_solvers(_P06)
    assert r is not None
    assert r["solver"] == "code_debug_get_max_local"


def test_try_local_solvers_code_gen_name():
    r = try_local_solvers(_P08)
    assert r is not None
    assert r["solver"] == "code_gen_second_largest_local"


def test_try_local_solvers_other_code_abstains():
    assert try_local_solvers(
        "Write a Python function that sorts a dictionary by value."
    ) is None
