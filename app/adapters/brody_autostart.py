"""Brody autostart — check liveness and optionally launch the Brody stack.

Environment variables (all optional, no defaults hardcoded):
  BRODY_ENDPOINT         URL used by brody_readonly.py (e.g. http://127.0.0.1:8000/api/brody/chat)
  BRODY_HEALTH_URL       Optional separate health probe URL; falls back to BRODY_ENDPOINT
  BRODY_TIMEOUT_S        Per-request timeout in seconds (default 2.0)
  BRODY_START_COMMAND    Shell command to launch the Brody stack (no default — never hardcoded)
  BRODY_START_TIMEOUT_S  Seconds to wait for the endpoint to come up after launch (default 20)

Liveness semantics:
  - URLs containing "/api/brody/chat" or "/brody/chat" are probed with a real POST
    (Content-Type: application/json).  The server must return HTTP 2xx AND a
    non-empty body.  A 405 or a plain TCP-open is NOT sufficient.
  - All other health URLs are probed with GET; 200/204 count as live.

Governance (immutable):
  No real action is taken other than launching the explicitly-supplied BRODY_START_COMMAND.
  No path is hardcoded.
  Public repo stays reproducible in stub mode without any env var set.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request

_DEFAULT_PROBE_TIMEOUT_S: float = 2.0
_DEFAULT_START_TIMEOUT_S: int = 20
_POLL_INTERVAL_S: float = 1.0

_BRODY_CHAT_SUFFIXES = ("/api/brody/chat", "/brody/chat")

_BRODY_HEALTH_PAYLOAD: bytes = json.dumps(
    {
        "message": "Brody readonly health check",
        "readonly": True,
        "mode": "health_check",
        "compact": True,
    },
    ensure_ascii=False,
).encode("utf-8")


def _is_brody_chat_url(url: str) -> bool:
    stripped = url.split("?")[0].rstrip("/")
    return any(stripped.endswith(s) for s in _BRODY_CHAT_SUFFIXES)


def _brody_endpoint() -> str:
    return os.environ.get("BRODY_ENDPOINT", "").strip()


def _health_url() -> str:
    hu = os.environ.get("BRODY_HEALTH_URL", "").strip()
    return hu if hu else _brody_endpoint()


def _probe_timeout() -> float:
    raw = os.environ.get("BRODY_TIMEOUT_S", "").strip()
    try:
        return float(raw) if raw else _DEFAULT_PROBE_TIMEOUT_S
    except ValueError:
        return _DEFAULT_PROBE_TIMEOUT_S


def _start_timeout() -> int:
    raw = os.environ.get("BRODY_START_TIMEOUT_S", "").strip()
    try:
        return int(raw) if raw else _DEFAULT_START_TIMEOUT_S
    except ValueError:
        return _DEFAULT_START_TIMEOUT_S


def endpoint_is_live(url: str, timeout_s: float | None = None) -> bool:
    """Return True if the endpoint is genuinely alive.

    For Brody chat URLs (/api/brody/chat, /brody/chat):
      - sends a POST with the health-check payload
      - requires HTTP 2xx AND non-empty response body
      - a 405 or mere port-open is NOT sufficient

    For all other URLs:
      - sends a GET
      - 200 or 204 is live; 405 is also accepted (server reachable, method mismatch
        is a routing detail, not a liveness issue)

    Never raises.
    """
    if not url:
        return False
    t = timeout_s if timeout_s is not None else _probe_timeout()

    if _is_brody_chat_url(url):
        return _probe_brody_chat(url, t)
    return _probe_generic_get(url, t)


def _probe_brody_chat(url: str, timeout_s: float) -> bool:
    """POST the health-check payload; require 2xx + non-empty body."""
    try:
        req = urllib.request.Request(
            url,
            data=_BRODY_HEALTH_PAYLOAD,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if not (200 <= resp.status < 300):
                return False
            body = resp.read()
            return bool(body and body.strip())
    except Exception:
        return False


def _probe_generic_get(url: str, timeout_s: float) -> bool:
    """GET probe; 200/204/405 = live (server is reachable)."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status in (200, 204)
    except urllib.error.HTTPError as exc:
        return exc.code in (200, 204, 405)
    except Exception:
        return False


def ensure_brody_live(
    auto_start: bool = False,
    require_live: bool = False,
) -> dict:
    """Check Brody endpoint liveness and optionally start the stack.

    Returns a status dict:
      {
        "attempted": bool,           # True if Popen was called
        "started": bool,             # True if process was launched
        "live_before": bool,         # Endpoint was already up before any action
        "live_after": bool,          # Endpoint is up after action
        "start_command_present": bool,
        "status": str,               # see STATUS_* below
        "error": str | None,
        "endpoint": str,
        "health_url": str,
      }

    Status values:
      "not_configured"        BRODY_ENDPOINT not set
      "live"                  Already live before any action
      "missing"               Not live, auto_start=False
      "start_command_missing" Not live, auto_start=True but BRODY_START_COMMAND absent
      "started_live"          Launched and Brody POST verified live within timeout
      "start_failed"          Launched but still unreachable after timeout
    """
    ep = _brody_endpoint()
    health = _health_url()
    start_cmd = os.environ.get("BRODY_START_COMMAND", "").strip()

    base: dict = {
        "attempted": False,
        "started": False,
        "live_before": False,
        "live_after": False,
        "start_command_present": bool(start_cmd),
        "status": "not_configured",
        "error": None,
        "endpoint": ep or "(not set)",
        "health_url": health or "(not set)",
    }

    if not ep:
        base["status"] = "not_configured"
        return base

    live_before = endpoint_is_live(health)
    base["live_before"] = live_before

    if live_before:
        base["live_after"] = True
        base["status"] = "live"
        return base

    if not auto_start:
        base["status"] = "missing"
        return base

    if not start_cmd:
        base["status"] = "start_command_missing"
        return base

    # Launch the start command
    base["attempted"] = True
    try:
        subprocess.Popen(start_cmd, shell=True)  # noqa: S603
        base["started"] = True
    except Exception as exc:
        base["status"] = "start_failed"
        base["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return base

    # Poll until the endpoint returns a genuine Brody response or timeout expires
    deadline = time.perf_counter() + _start_timeout()
    live_after = False
    while time.perf_counter() < deadline:
        if endpoint_is_live(health):
            live_after = True
            break
        time.sleep(_POLL_INTERVAL_S)

    base["live_after"] = live_after
    base["status"] = "started_live" if live_after else "start_failed"
    if not live_after:
        base["error"] = (
            f"Brody POST did not return 2xx+body within {_start_timeout()}s after launch"
        )
    return base
