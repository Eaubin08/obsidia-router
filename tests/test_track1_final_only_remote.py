"""Final-only Fireworks completion handling."""
from __future__ import annotations

import json

from app.adapters import fireworks
from benchmarks.track1_runner import track1_answer


class _FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _chat(monkeypatch, payload: dict, max_tokens: int):
    monkeypatch.setenv("FIREWORKS_API_KEY", "test-only-key")
    monkeypatch.setattr(
        fireworks.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(payload),
    )

    return fireworks.chat(
        "test-model",
        "test prompt",
        max_tokens=max_tokens,
        system="Final only.",
    )


def test_final_content_is_returned_without_private_reasoning(
    monkeypatch,
):
    result = _chat(
        monkeypatch,
        {
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "content": "Final answer.",
                    "reasoning_content": "private reasoning",
                },
            }],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 7,
                "total_tokens": 12,
            },
        },
        320,
    )

    assert result["text"] == "Final answer."
    assert result["finish_reason"] == "stop"
    assert result["final_content_present"] is True
    assert result["reasoning_content_present"] is True
    assert result["truncated"] is False
    assert result["error"] is None
    assert "private reasoning" not in result["text"]


def test_reasoning_only_at_cap_is_blocked(monkeypatch):
    result = _chat(
        monkeypatch,
        {
            "choices": [{
                "finish_reason": "length",
                "message": {
                    "content": None,
                    "reasoning_content": "private reasoning",
                },
            }],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 320,
                "total_tokens": 340,
            },
        },
        320,
    )

    assert result["text"] == "[error] no final answer content"
    assert result["final_content_present"] is False
    assert result["reasoning_content_present"] is True
    assert result["truncated"] is True
    assert result["error"] == "truncated_before_final_content"
    assert "private reasoning" not in result["text"]


def test_token_cap_detects_truncated_final(monkeypatch):
    result = _chat(
        monkeypatch,
        {
            "choices": [{
                "finish_reason": None,
                "message": {
                    "content": "Partial final answer"
                },
            }],
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 320,
                "total_tokens": 323,
            },
        },
        320,
    )

    assert result["final_content_present"] is True
    assert result["truncated"] is True
    assert result["error"] == "truncated_completion"


def test_track1_answer_rejects_missing_final_content():
    answer = track1_answer({
        "actual_route": "fireworks",
        "output": "[error] no final answer content",
        "final_content_present": False,
        "truncated": True,
    })

    assert answer == (
        "[error] Remote model produced no final answer."
    )


def test_track1_answer_rejects_truncated_final_content():
    answer = track1_answer({
        "actual_route": "fireworks",
        "output": "Partial final answer",
        "final_content_present": True,
        "truncated": True,
    })

    assert answer == (
        "[error] Remote model completion was truncated."
    )
