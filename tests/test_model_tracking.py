"""Tests — actual_model_used : propagation du modèle réel depuis run_one()."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from benchmarks.track1_remote_answer_contract import build_remote_answer_contract
from benchmarks.track1_runner import build_receipts, build_results


# ── 1. Contract model_preference ─────────────────────────────────────────────

def test_code_file_contract_model_preference_is_gpt_oss():
    c = build_remote_answer_contract("implement a python rate limiter with tests")
    assert c["model_preference"] == "accounts/fireworks/models/gpt-oss-120b"
    assert c["answer_kind"] == "code_file"


# ── 2. run_one — actual_model_used avec profil ────────────────────────────────

_MOCK_RESULT = {
    "text": "def rate_limit(): pass",
    "model": "accounts/fireworks/models/gpt-oss-120b",
    "total_tokens": 500,
    "prompt_tokens": 50,
    "completion_tokens": 450,
    "latency_s": 0.5,
    "dry_run": False,
    "fireworks_tokens": 450,
}

_GPT_OSS = "accounts/fireworks/models/gpt-oss-120b"
_DEEPSEEK = "accounts/fireworks/models/deepseek-v4-pro"


def test_run_one_stores_actual_model_used_when_profile_given():
    from app.cli import run_one
    from app.metrics.collector import MetricsCollector

    profile = {
        "profile": "CODE_FILE",
        "max_tokens": 1700,
        "system": "Answer with code only.",
        "model": _GPT_OSS,
    }
    metrics = MetricsCollector()

    with patch("app.adapters.fireworks.chat", return_value=_MOCK_RESULT):
        with patch("app.adapters.fireworks.allowed_models", return_value=None):
            decision = run_one(
                "implement a python rate limiter with tests",
                metrics,
                {},
                track1_profile=profile,
            )

    assert decision["route"] == "fireworks"
    assert decision["actual_model_used"] == _GPT_OSS


# ── 3. run_one — fallback quand contract model absent de l'allowed list ───────

def test_run_one_fallback_to_decision_model_when_contract_not_in_allowed():
    from app.cli import run_one
    from app.metrics.collector import MetricsCollector

    allowed_without_gpt = [_DEEPSEEK, "accounts/fireworks/models/glm-5p1"]
    profile = {
        "profile": "CODE_FILE",
        "max_tokens": 1700,
        "system": "Answer with code only.",
        "model": _GPT_OSS,
    }
    metrics = MetricsCollector()

    with patch("app.adapters.fireworks.chat", return_value=_MOCK_RESULT):
        with patch("app.adapters.fireworks.allowed_models", return_value=allowed_without_gpt):
            decision = run_one(
                "implement a python rate limiter with tests",
                metrics,
                {},
                track1_profile=profile,
            )

    assert decision["route"] == "fireworks"
    # gpt-oss absent de allowed → fallback sur le modèle router
    assert decision["actual_model_used"] != _GPT_OSS
    assert decision["actual_model_used"] == decision["model"]


# ── Helpers receipts/results ──────────────────────────────────────────────────

def _fw_row(actual_model: str, router_model: str = _DEEPSEEK) -> dict:
    return {
        "id": "fireworks_code",
        "request": "implement a rate limiter",
        "expected_route": "fireworks",
        "actual_route": "fireworks",
        "route_correct": True,
        "gate_verdict": "ALLOW",
        "gate_matched": "action",
        "level": 3,
        "model": router_model,
        "actual_model_used": actual_model,
        "intent_type": "question",
        "target_layer": "COMPUTE",
        "missing": [],
        "fireworks_tokens": 1429,
        "remote_call_avoided": False,
        "routing_latency_ms": 450.0,
        "output": "```python\ndef rate_limit(): pass\n```",
        "memory_entry": None,
        "topic_name": "general",
        "expected_response_profile": "CODE_FILE",
        "remote_answer_contract": None,
    }


# ── 4. build_receipts — champ actual_model_used présent ──────────────────────

def test_receipts_have_actual_model_used_field():
    row = _fw_row(actual_model=_GPT_OSS)
    receipts = build_receipts([row])
    task = receipts["tasks"][0]
    assert "actual_model_used" in task
    assert task["actual_model_used"] == _GPT_OSS


# ── 5. build_results — fireworks_model reflète actual_model_used ──────────────

def test_results_fireworks_model_uses_actual_model_used():
    row = _fw_row(actual_model=_GPT_OSS, router_model=_DEEPSEEK)
    results = build_results([row])
    task = results["tasks"][0]
    # L'appel réel était gpt-oss, pas deepseek
    assert task["fireworks_model"] == _GPT_OSS
    assert task["fireworks_model"] != _DEEPSEEK
