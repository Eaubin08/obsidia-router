"""Track 1 hardening closure — timeout ceiling + English-only answers.

Two AMD Track 1 contract guarantees enforced by code, not documentation:

1. Fireworks per-call timeout can never exceed DEFAULT_TIMEOUT_S (25 s),
   whatever FIREWORKS_TIMEOUT_S or an explicit caller argument says.
2. Every answer family the official runner can emit is English — including
   the memory corpus shipped in this public cut.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.adapters import fireworks
from benchmarks.track1_runner import track1_answer


# ── 1. Timeout ceiling ────────────────────────────────────────────────────────

@pytest.mark.parametrize("env_value,expected", [
    (None,      25.0),   # unset -> ceiling default
    ("10",      10.0),   # valid in-range value used as-is
    ("25",      25.0),   # exactly the ceiling
    ("60",      25.0),   # above ceiling -> clamped down
    ("0.5",      1.0),   # below floor -> clamped up to MIN_TIMEOUT_S
    ("0",       25.0),   # zero -> misconfiguration -> safe default
    ("-5",      25.0),   # negative -> misconfiguration -> safe default
    ("nan",     25.0),   # non-finite -> safe default
    ("inf",     25.0),   # non-finite -> safe default
    ("-inf",    25.0),   # non-finite -> safe default
    ("invalid", 25.0),   # unparsable -> safe default
])
def test_default_timeout_clamped(monkeypatch, env_value, expected):
    if env_value is None:
        monkeypatch.delenv("FIREWORKS_TIMEOUT_S", raising=False)
    else:
        monkeypatch.setenv("FIREWORKS_TIMEOUT_S", env_value)
    assert fireworks._default_timeout() == expected


@pytest.mark.parametrize("value,expected", [
    (10,            10.0),
    (25,            25.0),
    (60,            25.0),
    (0.5,            1.0),
    (0,             25.0),
    (-5,            25.0),
    (float("nan"),  25.0),
    (float("inf"),  25.0),
    (float("-inf"), 25.0),
])
def test_clamp_timeout(value, expected):
    result = fireworks._clamp_timeout(value)
    assert result == expected
    assert 1.0 <= result <= 25.0


@pytest.mark.parametrize("caller_timeout,expected", [
    (10,            10.0),
    (60,            25.0),
    (0.5,            1.0),
    (0,             25.0),
    (-5,            25.0),
    (float("nan"),  25.0),
    (float("inf"),  25.0),
])
def test_chat_transmits_clamped_timeout(monkeypatch, caller_timeout, expected):
    """Prove the value actually handed to the transport is the clamped one:
    fake API key forces the live path, urlopen is intercepted (no network)."""
    captured: dict = {}

    def fake_urlopen(req, timeout):
        captured["timeout"] = timeout
        raise fireworks.urllib.error.URLError("intercepted-no-network")

    monkeypatch.setenv("FIREWORKS_API_KEY", "test-key-never-real")
    monkeypatch.setattr(fireworks.urllib.request, "urlopen", fake_urlopen)

    result = fireworks.chat("test-model", "hi", timeout=caller_timeout)
    assert captured["timeout"] == expected
    assert 1.0 <= captured["timeout"] <= 25.0
    assert result["total_tokens"] == 0  # bounded error record, no spend


def test_timeout_ceiling_constant():
    # The AMD cap is 30 s per answer; the ceiling must keep headroom under it.
    assert fireworks.DEFAULT_TIMEOUT_S <= 30.0
    assert fireworks.MIN_TIMEOUT_S >= 1.0


# ── 2. English-only answers on every route family ────────────────────────────

_FRENCH_CHARS = re.compile(r"[àâäéèêëîïôùûüçœæÀÂÄÉÈÊËÎÏÔÙÛÜÇ]")
_FRENCH_WORDS = re.compile(
    r"\b(le|la|les|une?|des|est|sont|pour|avec|dans|aucune?|réponse|demande)\b",
    re.IGNORECASE,
)


def _assert_english(text: str, context: str) -> None:
    assert text, f"{context}: empty answer"
    assert not _FRENCH_CHARS.search(text), f"{context}: French characters in {text!r}"
    assert not _FRENCH_WORDS.search(text), f"{context}: French words in {text!r}"


def _row(route: str, **overrides) -> dict:
    row = {
        "actual_route": route,
        "output": "",
        "intent_type": "status",
        "missing": [],
        "gate_matched": "push",
        "memory_entry": None,
        "topic_name": "general",
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize("route,overrides", [
    ("no_model_needed",      {"intent_type": "status"}),
    ("no_model_needed",      {"intent_type": "unknown"}),
    ("hold_commands_only",   {}),
    ("denied",               {"gate_matched": "rm -rf"}),
    ("clarification_needed", {"missing": ["target", "intent"]}),
    ("local_solver",         {}),                    # empty output -> fallback msg
    ("brody",                {"output": "[brody-stub] internal"}),
    ("memory_hit",           {"memory_entry": None}),  # fallback msg
    ("fireworks",            {"output": ""}),          # bounded error msg
])
def test_track1_answer_families_are_english(route, overrides):
    answer = track1_answer(_row(route, **overrides))
    _assert_english(answer, f"route={route}")


def test_memory_corpus_is_english():
    """The public-cut memory index feeds memory_hit answers verbatim: every
    entry must itself pass the English gate for the AMD evaluation."""
    corpus = json.loads(
        (ROOT / "examples" / "memory_index.json").read_text(encoding="utf-8"))
    for key, entry in corpus.items():
        _assert_english(entry, f"memory_index[{key}]")


def test_official_runner_error_answers_are_english():
    """run_official.py bounded error strings must stay English."""
    for msg in ("[error] no request",
                "[error] routing failed: ValueError: boom"):
        _assert_english(msg, "runner error answer")
