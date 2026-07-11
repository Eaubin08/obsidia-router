"""LOT C — single parsing authority for ALLOWED_MODELS.

app.adapters.fireworks.allowed_models() is the only function allowed to
read the ALLOWED_MODELS environment variable. No network calls.
"""
from __future__ import annotations

import pytest

from app.adapters import fireworks


@pytest.mark.parametrize("env_value,expected", [
    (None,                              None),
    ("",                                None),
    ("small",                           ["small"]),
    ("small,medium,120b",               ["small", "medium", "120b"]),
    ("  small , medium ,, 120b ",       ["small", "medium", "120b"]),
    ("120b,small",                      ["120b", "small"]),  # order is authority
])
def test_allowed_models_parsing(monkeypatch, env_value, expected):
    if env_value is None:
        monkeypatch.delenv("ALLOWED_MODELS", raising=False)
    else:
        monkeypatch.setenv("ALLOWED_MODELS", env_value)
    assert fireworks.allowed_models() == expected


def test_allowed_models_duplicate_keeps_first_occurrence_order(monkeypatch):
    """Doctrine: duplicates are de-duped, keeping the first occurrence and
    its original position — a name repeated later never re-promotes rank."""
    monkeypatch.setenv("ALLOWED_MODELS", "small,medium,small,120b,medium")
    assert fireworks.allowed_models() == ["small", "medium", "120b"]


def test_allowed_models_all_whitespace_is_none(monkeypatch):
    monkeypatch.setenv("ALLOWED_MODELS", "   ")
    assert fireworks.allowed_models() is None


def test_allowed_models_only_commas_is_none(monkeypatch):
    monkeypatch.setenv("ALLOWED_MODELS", ",,,")
    assert fireworks.allowed_models() is None


def test_allowed_models_single_entry(monkeypatch):
    monkeypatch.setenv("ALLOWED_MODELS", "only-one-model")
    assert fireworks.allowed_models() == ["only-one-model"]
