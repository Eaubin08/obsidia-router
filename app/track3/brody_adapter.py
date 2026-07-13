"""Track 3 Brody readonly adapter — thin, no-autostart wrapper.

Differences from the shared app/adapters/brody_readonly.py:
  - No stub fallback as answer (brody_stub is route_marker_only in Track 3).
  - No autostart (never launches the Brody service).
  - Loopback validation (non-loopback BRODY_ENDPOINT is rejected).
  - Single attempt, bounded timeout.
  - Returns success=False when unavailable; caller must continue to Qwen.

Env vars:
  BRODY_ENDPOINT     — full POST URL, e.g. http://127.0.0.1:PORT/api/brody/chat
  BRODY_T3_TIMEOUT_S — float, default 2.0
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

_ALLOWED_LOOPBACK_HOSTS: frozenset[str] = frozenset(
    {"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"}
)
_DEFAULT_TIMEOUT_S: float = 2.0

_GOVERNANCE_EXPECTED: dict[str, object] = {
    "decision_authority": "KX108_ONLY",
    "emits_act":          False,
    "memory_write":       False,
    "kernel_mutation":    False,
    "advisory_only":      True,
}


def _get_endpoint() -> str:
    return os.environ.get("BRODY_ENDPOINT", "").strip()


def _get_timeout() -> float:
    raw = os.environ.get("BRODY_T3_TIMEOUT_S", "").strip()
    try:
        return float(raw) if raw else _DEFAULT_TIMEOUT_S
    except ValueError:
        return _DEFAULT_TIMEOUT_S


def _validate_loopback(endpoint: str) -> None:
    host = urlparse(endpoint).hostname or ""
    if host not in _ALLOWED_LOOPBACK_HOSTS:
        raise ValueError(
            f"brody_adapter: endpoint host {host!r} is not loopback — "
            "Track 3 only allows local Brody readonly endpoints"
        )


def is_available(timeout: float = 1.0) -> bool:
    """True only when BRODY_ENDPOINT is set, is loopback, and passes health check."""
    endpoint = _get_endpoint()
    if not endpoint:
        return False
    try:
        _validate_loopback(endpoint)
        parsed = urlparse(endpoint)
        health_url = f"{parsed.scheme}://{parsed.netloc}/health"
        with urllib.request.urlopen(health_url, timeout=timeout):
            return True
    except Exception:
        return False


def _extract_text(data: dict, raw_bytes: str) -> str:
    for key in ("response", "final_answer", "text", "answer"):
        val = data.get(key)
        if val and isinstance(val, str):
            return val.strip()
    return raw_bytes[:500]


def chat(prompt: str, timeout: float | None = None) -> dict:
    """Single readonly call to the Brody endpoint.

    Returns:
        {
            "success":      bool,
            "text":         str,
            "elapsed_ms":   float,
            "brody_mode":   "live",
            "governance_ok": bool,
            "error":        str | None,
        }
    Never raises; returns success=False on any failure or unavailability.
    """
    t0 = time.perf_counter()
    endpoint = _get_endpoint()
    timeout_ = timeout if timeout is not None else _get_timeout()

    def _err(msg: str) -> dict:
        return {
            "success":      False,
            "text":         "",
            "elapsed_ms":   round((time.perf_counter() - t0) * 1000, 2),
            "brody_mode":   "unavailable",
            "governance_ok": False,
            "error":        msg,
        }

    if not endpoint:
        return _err("BRODY_ENDPOINT not set")

    try:
        _validate_loopback(endpoint)
    except ValueError as exc:
        return _err(str(exc))

    payload = json.dumps(
        {"message": prompt, "readonly": True, "mode": "readonly_stack_test", "compact": True},
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_) as resp:
            body = resp.read()
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            raw_str = body.decode("utf-8", errors="replace")
            try:
                data = json.loads(raw_str) if body else {}
            except Exception:
                data = {}

            text = _extract_text(data, raw_str)

            gov_ok = all(
                data.get(k) == v
                for k, v in _GOVERNANCE_EXPECTED.items()
                if k in data
            )

            return {
                "success":      bool(text),
                "text":         text,
                "elapsed_ms":   elapsed_ms,
                "brody_mode":   "live",
                "governance_ok": gov_ok,
                "error":        None,
            }
    except Exception as exc:
        return _err(f"{type(exc).__name__}: {str(exc)[:120]}")
