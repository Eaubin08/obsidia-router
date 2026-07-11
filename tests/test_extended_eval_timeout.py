"""Tests LOT G4 — timeout d'évaluation étendu borné (60 s).

Le chemin ordinaire garde le plafond 25 s. Seul un appel d'évaluation
explicitement marqué allow_extended_timeout=True peut atteindre 60 s.
Le timeout illimité reste interdit.
"""

import pytest

from app.adapters import fireworks


def test_eval_ceiling_is_60():
    assert fireworks.EVAL_TIMEOUT_CEILING_S == 60.0


def test_ordinary_ceiling_unchanged():
    assert fireworks.DEFAULT_TIMEOUT_S == 25.0


@pytest.mark.parametrize("value,expected", [
    (60.0, 60.0),
    (45.0, 45.0),
    (300.0, 60.0),      # au-delà du plafond eval -> clampé à 60
    (float("inf"), 60.0),
    (-5.0, 60.0),
    (0.5, 1.0),
])
def test_clamp_with_eval_ceiling(value, expected):
    assert fireworks._clamp_timeout(
        value, fireworks.EVAL_TIMEOUT_CEILING_S) == expected


@pytest.mark.parametrize("value,expected", [
    (60.0, 25.0),       # sans flag, 60 est clampé à 25
    (30.0, 25.0),
    (10.0, 10.0),
])
def test_clamp_default_ceiling_still_25(value, expected):
    assert fireworks._clamp_timeout(value) == expected


def test_chat_ordinary_path_clamps_to_25(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["timeout"] = timeout
        raise TimeoutError("test")

    monkeypatch.setenv("FIREWORKS_API_KEY", "test-key")
    monkeypatch.setattr(
        "urllib.request.urlopen", fake_urlopen)
    result = fireworks.chat("m", "p", timeout=60.0)
    assert captured["timeout"] == 25.0
    assert result["error"]


def test_chat_extended_path_allows_60(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["timeout"] = timeout
        raise TimeoutError("test")

    monkeypatch.setenv("FIREWORKS_API_KEY", "test-key")
    monkeypatch.setattr(
        "urllib.request.urlopen", fake_urlopen)
    fireworks.chat("m", "p", timeout=60.0, allow_extended_timeout=True)
    assert captured["timeout"] == 60.0


def test_chat_extended_path_never_exceeds_60(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["timeout"] = timeout
        raise TimeoutError("test")

    monkeypatch.setenv("FIREWORKS_API_KEY", "test-key")
    monkeypatch.setattr(
        "urllib.request.urlopen", fake_urlopen)
    fireworks.chat("m", "p", timeout=999.0, allow_extended_timeout=True)
    assert captured["timeout"] == 60.0
