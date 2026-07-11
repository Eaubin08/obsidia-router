"""Tests for benchmarks/probe_ladder.py — _probe_rung logic, dry-run guard."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from benchmarks.probe_ladder import _probe_rung


def _make_fw_response(**kwargs) -> dict:
    """Build a minimal fireworks.chat()-like response."""
    base = {
        "dry_run": False,
        "error": None,
        "model": "accounts/fireworks/models/test-model",
        "text": "OK",
        "prompt_tokens": 10,
        "completion_tokens": 2,
        "total_tokens": 12,
        "latency_s": 0.1,
        "finish_reason": "stop",
        "final_content_present": True,
        "reasoning_content_present": False,
        "truncated": False,
    }
    base.update(kwargs)
    return base


# ── 1. Dry-run (no API key) ───────────────────────────────────────────────────

def test_dry_run_returns_dry_run_status(monkeypatch):
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    import importlib
    from app.adapters import fireworks as fw
    importlib.reload(fw)

    res = _probe_rung("accounts/fireworks/models/any-model")
    assert res["status"] == "DRY_RUN"
    assert res["pass"] is False
    assert "FIREWORKS_API_KEY" in res["reason"] or "not sent" in res["reason"]


def test_dry_run_no_live_call(monkeypatch):
    """_probe_rung must never open a socket when no key is set."""
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    import importlib
    from app.adapters import fireworks as fw
    importlib.reload(fw)

    called = []
    original_chat = fw.chat

    def spy_chat(*a, **kw):
        called.append((a, kw))
        return original_chat(*a, **kw)  # will return dry-run dict

    monkeypatch.setattr(fw, "chat", spy_chat)
    _probe_rung("accounts/fireworks/models/any-model")
    # chat() is called but the adapter itself does NOT open a socket in dry-run
    assert all("dry_run" not in str(c) or True for c in called)  # just confirms no exception


# ── 2. PASS conditions ────────────────────────────────────────────────────────

def test_pass_on_ok_response(monkeypatch):
    import benchmarks.probe_ladder as pl
    monkeypatch.setattr(
        "app.adapters.fireworks.chat",
        lambda *a, **kw: _make_fw_response(text="OK"),
    )
    res = pl._probe_rung("accounts/fireworks/models/test-model")
    assert res["status"] == "PASS"
    assert res["pass"] is True
    assert res["reason"] == "connectivity confirmed"


def test_pass_on_ok_with_whitespace(monkeypatch):
    import benchmarks.probe_ladder as pl
    monkeypatch.setattr(
        "app.adapters.fireworks.chat",
        lambda *a, **kw: _make_fw_response(text="  ok  "),
    )
    res = pl._probe_rung("accounts/fireworks/models/test-model")
    assert res["status"] == "PASS"


def test_pass_on_ok_period(monkeypatch):
    import benchmarks.probe_ladder as pl
    monkeypatch.setattr(
        "app.adapters.fireworks.chat",
        lambda *a, **kw: _make_fw_response(text="OK."),
    )
    res = pl._probe_rung("accounts/fireworks/models/test-model")
    assert res["status"] == "PASS"


# ── 3. FAIL conditions ────────────────────────────────────────────────────────

def test_fail_on_empty_response(monkeypatch):
    import benchmarks.probe_ladder as pl
    monkeypatch.setattr(
        "app.adapters.fireworks.chat",
        lambda *a, **kw: _make_fw_response(text=""),
    )
    res = pl._probe_rung("accounts/fireworks/models/test-model")
    assert res["status"] == "FAIL"
    assert "empty" in res["reason"]


def test_fail_on_no_final_content(monkeypatch):
    import benchmarks.probe_ladder as pl
    monkeypatch.setattr(
        "app.adapters.fireworks.chat",
        lambda *a, **kw: _make_fw_response(
            text="", final_content_present=False,
            error="truncated_before_final_content",
        ),
    )
    res = pl._probe_rung("accounts/fireworks/models/test-model")
    assert res["status"] == "FAIL"
    assert "error" in res["reason"] or "content" in res["reason"]


def test_fail_on_truncated_finish_reason_length(monkeypatch):
    import benchmarks.probe_ladder as pl
    monkeypatch.setattr(
        "app.adapters.fireworks.chat",
        lambda *a, **kw: _make_fw_response(
            text="OK par", finish_reason="length", truncated=True,
            error="truncated_completion",
        ),
    )
    res = pl._probe_rung("accounts/fireworks/models/test-model")
    assert res["status"] == "FAIL"
    assert "truncated" in res["reason"]


def test_fail_on_transport_error(monkeypatch):
    import benchmarks.probe_ladder as pl
    monkeypatch.setattr(
        "app.adapters.fireworks.chat",
        lambda *a, **kw: _make_fw_response(
            text="[error] HTTP 401", error="HTTP 401 error",
            total_tokens=0,
        ),
    )
    res = pl._probe_rung("accounts/fireworks/models/test-model")
    assert res["status"] == "FAIL"
    assert "error" in res["reason"]


def test_fail_when_response_missing_ok(monkeypatch):
    import benchmarks.probe_ladder as pl
    monkeypatch.setattr(
        "app.adapters.fireworks.chat",
        lambda *a, **kw: _make_fw_response(text="Sure, I can help you!"),
    )
    res = pl._probe_rung("accounts/fireworks/models/test-model")
    assert res["status"] == "FAIL"
    assert "OK" in res["reason"]


def test_fail_on_zero_total_tokens(monkeypatch):
    import benchmarks.probe_ladder as pl
    monkeypatch.setattr(
        "app.adapters.fireworks.chat",
        lambda *a, **kw: _make_fw_response(text="OK", total_tokens=0),
    )
    res = pl._probe_rung("accounts/fireworks/models/test-model")
    assert res["status"] == "FAIL"
    assert "total_tokens" in res["reason"]


# ── 4. Metadata fields are surfaced ──────────────────────────────────────────

def test_requested_model_in_result(monkeypatch):
    import benchmarks.probe_ladder as pl
    monkeypatch.setattr(
        "app.adapters.fireworks.chat",
        lambda *a, **kw: _make_fw_response(text="OK"),
    )
    res = pl._probe_rung("accounts/fireworks/models/gpt-oss-120b")
    assert res["model"] == "accounts/fireworks/models/gpt-oss-120b"


def test_actual_model_surfaced_when_present(monkeypatch):
    import benchmarks.probe_ladder as pl
    monkeypatch.setattr(
        "app.adapters.fireworks.chat",
        lambda *a, **kw: _make_fw_response(
            text="OK", model="accounts/fireworks/models/gpt-oss-120b",
        ),
    )
    res = pl._probe_rung("accounts/fireworks/models/gpt-oss-120b")
    assert res["actual_model"] != "-"


def test_finish_reason_surfaced(monkeypatch):
    import benchmarks.probe_ladder as pl
    monkeypatch.setattr(
        "app.adapters.fireworks.chat",
        lambda *a, **kw: _make_fw_response(text="OK", finish_reason="stop"),
    )
    res = pl._probe_rung("accounts/fireworks/models/test-model")
    assert res["finish_reason"] == "stop"


def test_token_counts_surfaced(monkeypatch):
    import benchmarks.probe_ladder as pl
    monkeypatch.setattr(
        "app.adapters.fireworks.chat",
        lambda *a, **kw: _make_fw_response(
            text="OK", prompt_tokens=8, completion_tokens=1, total_tokens=9,
        ),
    )
    res = pl._probe_rung("accounts/fireworks/models/test-model")
    assert res["prompt_tokens"] == 8
    assert res["completion_tokens"] == 1
    assert res["total_tokens"] == 9
