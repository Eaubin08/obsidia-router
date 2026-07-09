"""Post-process code extraction — _extract_code_block safety net.

Verifies that the post-processor correctly strips preamble prose from
Fireworks responses before grading, without touching local-solver output
or non-code responses.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks.answer_accuracy import _extract_code_block  # noqa: E402


# ── ```python fence extraction ────────────────────────────────────────────────

def test_extracts_python_fence():
    raw = (
        "We need to write a function.\n\n"
        "```python\n"
        "def second_largest(nums):\n"
        "    return sorted(set(nums))[-2]\n"
        "```\n\n"
        "This handles duplicates by using a set."
    )
    result = _extract_code_block(raw)
    assert result.startswith("def second_largest")
    assert "We need to" not in result
    assert "This handles" not in result


def test_extracts_bare_fence():
    raw = (
        "Here is the solution:\n"
        "```\n"
        "def second_largest(nums):\n"
        "    first = second = float('-inf')\n"
        "    for n in nums:\n"
        "        if n > first: second, first = first, n\n"
        "        elif first > n > second: second = n\n"
        "    return second\n"
        "```"
    )
    result = _extract_code_block(raw)
    assert result.startswith("def second_largest")
    assert "Here is" not in result


# ── def-based extraction (no fence) ──────────────────────────────────────────

def test_extracts_from_def_when_no_fence():
    raw = (
        "To solve this, we iterate.\n\n"
        "def second_largest(nums):\n"
        "    nums = sorted(set(nums), reverse=True)\n"
        "    return nums[1]\n"
    )
    result = _extract_code_block(raw)
    assert result.startswith("def second_largest")
    assert "To solve this" not in result


def test_keeps_imports_before_def():
    raw = (
        "Explanation.\n\n"
        "```python\n"
        "import heapq\n\n"
        "def second_largest(nums):\n"
        "    return heapq.nlargest(2, set(nums))[-1]\n"
        "```"
    )
    result = _extract_code_block(raw)
    assert "import heapq" in result
    assert "def second_largest" in result
    assert "Explanation" not in result


# ── non-code responses untouched ─────────────────────────────────────────────

def test_non_code_returned_unchanged():
    raw = "The sentiment is positive — the text uses 'great' and 'wonderful'."
    assert _extract_code_block(raw) == raw


def test_empty_returns_empty():
    assert _extract_code_block("") == ""


def test_plain_def_no_preamble_unchanged():
    raw = "def second_largest(nums):\n    return max(set(nums) - {max(nums)})\n"
    result = _extract_code_block(raw)
    assert result.startswith("def second_largest")


# ── grading regex still matches after extraction ─────────────────────────────

_GRADE_CHECKS = [
    re.compile(r"def\s+\w+", re.I | re.M),
    re.compile(
        r"sorted|sort\b|max\s*\(|set\s*\(|heapq|nlargest|unique"
        r"|float\s*\(|second\s*=|-inf\b|counter|remove\b|index\b",
        re.I | re.M,
    ),
]


def _grade(code: str) -> bool:
    return all(rx.search(code) for rx in _GRADE_CHECKS)


def test_sorted_set_passes_grading():
    code = "def second_largest(nums):\n    return sorted(set(nums))[-2]\n"
    assert _grade(_extract_code_block(code))


def test_linear_scan_passes_grading():
    code = (
        "def second_largest(nums):\n"
        "    first = second = float('-inf')\n"
        "    for n in nums:\n"
        "        if n > first: second, first = first, n\n"
        "        elif first > n > second: second = n\n"
        "    return second\n"
    )
    assert _grade(_extract_code_block(code))


def test_max_set_passes_grading():
    code = (
        "def second_largest(nums):\n"
        "    unique = list(set(nums))\n"
        "    unique.remove(max(unique))\n"
        "    return max(unique)\n"
    )
    assert _grade(_extract_code_block(code))


def test_preamble_plus_sorted_set_passes_grading():
    raw = (
        "We need to write a Python function.\n\n"
        "```python\n"
        "def second_largest(nums):\n"
        "    return sorted(set(nums))[-2]\n"
        "```"
    )
    assert _grade(_extract_code_block(raw))


def test_pure_prose_fails_grading():
    raw = "The second largest number in a list can be found by sorting it."
    assert not _grade(_extract_code_block(raw))
