"""Brody readonly adapter — HTTP live bridge with stub fallback.

Live mode  (BRODY_ENDPOINT set):
  POST to BRODY_ENDPOINT with the readonly stack-test payload.
  Timeout from BRODY_TIMEOUT_S (default 2.0 s).
  Returns brody_mode="live".

Stub mode (BRODY_ENDPOINT absent or request fails):
  Falls back to the existing stub contract.
  Returns brody_mode="stub" or brody_mode="fallback".

Payload (aligns with the real /api/brody/chat contract):
  {
    "message": <ir.raw>,
    "readonly": true,
    "mode": "readonly_stack_test",
    "compact": true
  }

Response parsing priority:
  response > final_answer > text > answer > raw[:500]

Governance validation (non-blocking — missing fields are accepted):
  If a governance field is present in the response, it must match the
  expected value; a mismatch is logged as a warning but does NOT fail
  the call (the router's own _GOVERNANCE constants take precedence).

Governance (immutable):
  real_action=false, memory_write=false, kernel_mutation=false,
  emits_act=false, decision_authority=KX108_ONLY

Never raises: all exceptions are caught and trigger stub fallback.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from app.adapters.brody_stub import answer as _stub_answer

_GOVERNANCE = {
    "real_action": False,
    "memory_write": False,
    "kernel_mutation": False,
    "emits_act": False,
    "decision_authority": "KX108_ONLY",
}

# Expected governance values from the real Brody response.
# Presence is optional; when present the value must match.
_GOVERNANCE_CHECKS: dict[str, object] = {
    "decision_authority": "KX108_ONLY",
    "emits_act": False,
    "memory_write": False,
    "graphiti_write": False,
    "kernel_mutation": False,
    "advisory_only": True,
}

_DEFAULT_TIMEOUT_S: float = 2.0

_metrics: dict = {
    "brody_live_calls": 0,
    "brody_stub_fallbacks": 0,
    "brody_errors": 0,
    "brody_total_latency_ms": 0.0,
}


def _endpoint() -> str:
    return os.environ.get("BRODY_ENDPOINT", "").strip()


def _timeout() -> float:
    raw = os.environ.get("BRODY_TIMEOUT_S", "").strip()
    try:
        return float(raw) if raw else _DEFAULT_TIMEOUT_S
    except ValueError:
        return _DEFAULT_TIMEOUT_S


def _extract_text(data: dict, raw_bytes: str) -> str:
    """Extract the best available text field from Brody's response."""
    for key in ("response", "final_answer", "text", "answer"):
        val = data.get(key)
        if val and isinstance(val, str):
            return val
    return raw_bytes[:500]


def _check_governance_warnings(data: dict) -> list[str]:
    """Return a list of governance mismatches (non-fatal, informational only)."""
    warnings: list[str] = []
    for field, expected in _GOVERNANCE_CHECKS.items():
        if field in data and data[field] != expected:
            warnings.append(f"{field}={data[field]!r} (expected {expected!r})")
    return warnings


def _live_call(message: str) -> dict:
    url = _endpoint()
    payload = json.dumps(
        {
            "message": message,
            "readonly": True,
            "mode": "readonly_stack_test",
            "compact": True,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=_timeout()) as resp:
        body = resp.read()
        latency_ms = (time.perf_counter() - t0) * 1000
        raw_str = body.decode("utf-8", errors="replace")
        try:
            data = json.loads(raw_str) if body else {}
        except Exception:
            data = {}

        text = _extract_text(data, raw_str)
        gov_warnings = _check_governance_warnings(data)

        result: dict = {
            "organ": "brody",
            "text": text,
            "remote_tokens": 0,
            "brody_mode": "live",
            "brody_latency_ms": round(latency_ms, 2),
            **_GOVERNANCE,
        }
        if gov_warnings:
            result["brody_gov_warnings"] = gov_warnings
        # Include a compact raw snapshot for traceability
        raw_keys = {k: data[k] for k in (
            "voice_runtime", "fastpath", "decision_authority",
            "emits_act", "advisory_only", "memory_write",
            "graphiti_write", "kernel_mutation",
        ) if k in data}
        if raw_keys:
            result["raw"] = raw_keys
        return result


def answer(ir: dict, topic: dict) -> dict:
    """Bounded Brody response: live HTTP if BRODY_ENDPOINT set, else stub.

    Never raises. Returns dict with brody_mode, governance fields and metrics.
    """
    ep = _endpoint()
    t0 = time.perf_counter()

    if ep:
        try:
            result = _live_call(ir.get("raw", ""))
            _metrics["brody_live_calls"] += 1
            _metrics["brody_total_latency_ms"] += result.get("brody_latency_ms", 0.0)
            return result
        except Exception as exc:
            _metrics["brody_errors"] += 1
            _metrics["brody_stub_fallbacks"] += 1
            stub = _stub_answer(ir, topic)
            latency_ms = (time.perf_counter() - t0) * 1000
            _metrics["brody_total_latency_ms"] += latency_ms
            return {
                **stub,
                "brody_mode": "fallback",
                "brody_fallback_reason": f"{type(exc).__name__}: {str(exc)[:120]}",
                "brody_latency_ms": round(latency_ms, 2),
                **_GOVERNANCE,
            }

    _metrics["brody_stub_fallbacks"] += 1
    stub = _stub_answer(ir, topic)
    latency_ms = (time.perf_counter() - t0) * 1000
    _metrics["brody_total_latency_ms"] += latency_ms
    return {
        **stub,
        "brody_mode": "stub",
        "brody_latency_ms": round(latency_ms, 2),
        **_GOVERNANCE,
    }


def get_metrics() -> dict:
    """Return accumulated Brody metrics (cumulative since process start)."""
    calls = _metrics["brody_live_calls"] + _metrics["brody_stub_fallbacks"]
    avg_ms = (
        round(_metrics["brody_total_latency_ms"] / calls, 2) if calls else 0.0
    )
    return {
        "brody_live_calls": _metrics["brody_live_calls"],
        "brody_stub_fallbacks": _metrics["brody_stub_fallbacks"],
        "brody_errors": _metrics["brody_errors"],
        "brody_latency_ms_avg": avg_ms,
        "brody_mode": "live" if _metrics["brody_live_calls"] > 0 else "stub",
    }


def reset_metrics() -> None:
    """Reset cumulative metrics (useful between test runs)."""
    _metrics["brody_live_calls"] = 0
    _metrics["brody_stub_fallbacks"] = 0
    _metrics["brody_errors"] = 0
    _metrics["brody_total_latency_ms"] = 0.0
