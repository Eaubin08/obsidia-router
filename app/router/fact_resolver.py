"""Canonical boot knowledge fact resolver — readonly, no write, no network.

This module holds a curated pack of verifiable canonical geographic facts.
It is NOT dynamic memory, NOT user memory, NOT Graphiti, NOT session state.
It is architectural knowledge compiled once at build time, read-only at
runtime, and never mutated by any request.

canonical boot knowledge — no write
decision_authority: KX108_ONLY
memory_write: false
kernel_mutation: false
"""
from __future__ import annotations

import re

# ── Canonical fact pack (readonly, all facts verifiable offline) ──────────────
# canonical boot knowledge — no write

_GEO_FACTS: dict[str, dict] = {
    "australia": {
        "capital": "Canberra",
        "nearby_water": "Lake Burley Griffin",
        "answer_capital_water": (
            "Canberra is the capital of Australia. "
            "It is situated near Lake Burley Griffin."
        ),
        "answer_capital_only": (
            "Canberra is the capital of Australia, "
            "located near Lake Burley Griffin."
        ),
    },
    "france": {
        "capital": "Paris",
        "nearby_water": "River Seine",
        "answer_capital_water": (
            "Paris is the capital of France. "
            "It is situated along the River Seine."
        ),
        "answer_capital_only": "Paris is the capital of France.",
    },
    "japan": {
        "capital": "Tokyo",
        "nearby_water": "Tokyo Bay",
        "answer_capital_water": (
            "Tokyo is the capital of Japan. "
            "It is situated near Tokyo Bay."
        ),
        "answer_capital_only": "Tokyo is the capital of Japan.",
    },
    "germany": {
        "capital": "Berlin",
        "nearby_water": "River Spree",
        "answer_capital_water": (
            "Berlin is the capital of Germany. "
            "It is situated along the River Spree."
        ),
        "answer_capital_only": "Berlin is the capital of Germany.",
    },
}

# ── Trigger patterns ──────────────────────────────────────────────────────────

_FACT_Q_TRIGGER = re.compile(
    r"\b(what|where|which|who)\b", re.I)

_CAPITAL_TRIGGER = re.compile(
    r"\bcapital\b", re.I)

_WATER_TRIGGER = re.compile(
    r"\b(lake|body of water|river|sea|bay|ocean|water)\b", re.I)

_COUNTRY_PATTERNS: dict[str, re.Pattern] = {
    "australia": re.compile(r"\baustralia\b|\bcanberra\b", re.I),
    "france": re.compile(r"\bfrance\b|\bparis\b", re.I),
    "japan": re.compile(r"\bjapan\b|\btokyo\b", re.I),
    "germany": re.compile(r"\bgermany\b|\bberlin\b", re.I),
}


def solve_fact(raw: str) -> str | None:
    """Canonical boot knowledge resolver.

    Answers only when the question clearly maps to a known canonical fact.
    Abstains on anything not in the pack, any ambiguity, or non-geographic
    questions. No write, no network, no dynamic memory.

    canonical boot knowledge — no write
    """
    if not _FACT_Q_TRIGGER.search(raw):
        return None
    if not _CAPITAL_TRIGGER.search(raw):
        return None

    # Match against known countries
    for country, pattern in _COUNTRY_PATTERNS.items():
        if pattern.search(raw):
            fact = _GEO_FACTS[country]
            if _WATER_TRIGGER.search(raw):
                return fact["answer_capital_water"]
            return fact["answer_capital_only"]

    return None
