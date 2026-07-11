"""Fireworks AI adapter — the ONLY place where remote tokens are spent.

OpenAI-compatible chat completion over the Fireworks API. Stdlib only.

Environment:
  FIREWORKS_API_KEY   required for live calls; without it the adapter runs
                      in dry-run mode (decision + estimate, no network)
  FIREWORKS_BASE_URL  default https://api.fireworks.ai/inference/v1
  ALLOWED_MODELS      optional comma-separated ladder, cheapest first;
                      overrides the default ladder for scoring harnesses
  FIREWORKS_TIMEOUT_S per-call timeout in seconds (default 25.0). Clamped to
                      [1.0, 25.0] — the 30 s per-answer AMD Track 1 cap can
                      never be exceeded, whatever the environment says.

Headers sent on every request:
  Authorization: Bearer <key>
  Content-Type: application/json
  Accept: application/json
  User-Agent: obsidia-router/track1-benchmark
  (Cloudflare blocks Python-urllib default UA with 403/1010 — explicit UA required)
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.fireworks.ai/inference/v1"

# AMD Track 1 caps each answer at 30 s; keep headroom for routing + I/O.
# DEFAULT_TIMEOUT_S is a hard ceiling: no environment value may raise it.
DEFAULT_TIMEOUT_S = 25.0
MIN_TIMEOUT_S = 1.0

# LOT G4 — bounded extended timeout for comparative evaluation ONLY
# (direct baseline, model matrix, quality comparison). The official runner
# and the ordinary Obsidia path never pass allow_extended_timeout and keep
# the 25 s ceiling. Unlimited timeouts remain forbidden.
EVAL_TIMEOUT_CEILING_S = 60.0


def _clamp_timeout(value: float, ceiling: float = DEFAULT_TIMEOUT_S) -> float:
    """Normalize any timeout to [MIN_TIMEOUT_S, ceiling].

    Single doctrine for env values and explicit caller arguments:
      - NaN / +-inf / <= 0  -> ceiling (misconfiguration: zero or
        negative would either hang forever or fail instantly — safe ceiling)
      - 0 < value < 1       -> MIN_TIMEOUT_S
      - value > ceiling     -> ceiling
      - otherwise           -> value unchanged

    ceiling defaults to DEFAULT_TIMEOUT_S (25 s, ordinary path). Evaluation
    callers may raise it up to EVAL_TIMEOUT_CEILING_S via chat()'s
    allow_extended_timeout flag — never beyond.
    """
    if not math.isfinite(value) or value <= 0:
        return ceiling
    return min(max(value, MIN_TIMEOUT_S), ceiling)


def _default_timeout() -> float:
    raw = os.environ.get("FIREWORKS_TIMEOUT_S", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_S
    return _clamp_timeout(value)


def allowed_models() -> list[str] | None:
    """Single parsing authority for ALLOWED_MODELS (LOT C).

    Every other module that needs the allowlist must call this function
    instead of reading os.environ directly.

    Doctrine:
      - absent or blank    -> None (caller falls back to its own default
                               ladder; never an empty list)
      - non-empty          -> comma-split, each entry stripped, blank
                               entries dropped, order preserved exactly as
                               provided (index 0 stays the harness's stated
                               cheapest/first-choice model)
      - duplicate entries  -> only the first occurrence is kept (stable
                               de-dup); a name repeated later never
                               re-promotes its rung or reorders the ladder
    """
    raw = os.environ.get("ALLOWED_MODELS", "").strip()
    if not raw:
        return None
    seen: set[str] = set()
    ordered: list[str] = []
    for entry in raw.split(","):
        name = entry.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered or None


def estimate_tokens(text: str) -> int:
    """Deterministic estimate used for 'tokens saved' accounting: ~4 chars/token
    plus a typical bounded completion."""
    return len(text) // 4 + 300


def extract_text(data: dict) -> str:
    """Return only final answer content.

    Private ``reasoning_content`` is never eligible as a judged answer.
    """
    choices = data.get("choices") or []
    if not choices:
        return "[error] no choices in response"

    message = choices[0].get("message") or {}
    content = message.get("content")

    if isinstance(content, str) and content.strip():
        return content

    return "[error] no final answer content"

def chat(model: str, prompt: str, max_tokens: int = 512,
         system: str | None = None, timeout: float | None = None,
         allow_extended_timeout: bool = False) -> dict:
    """One chat completion. Returns text + real token usage, or a dry-run
    record when no API key is configured.

    allow_extended_timeout (LOT G4): evaluation-only flag. When True, an
    explicit timeout may reach EVAL_TIMEOUT_CEILING_S (60 s) instead of the
    ordinary 25 s ceiling. Reserved for direct-baseline capture, model
    matrix, and quality comparison — never the official runner path.
    """
    ceiling = EVAL_TIMEOUT_CEILING_S if allow_extended_timeout else DEFAULT_TIMEOUT_S
    if timeout is None:
        timeout = _default_timeout()
    else:
        # same doctrine as the env path: [1, ceiling] s, non-finite/<=0 -> ceiling
        timeout = _clamp_timeout(timeout, ceiling)
    api_key = os.environ.get("FIREWORKS_API_KEY", "").strip()
    if not api_key:
        return {
            "dry_run": True,
            "model": model,
            "text": "[dry-run] no FIREWORKS_API_KEY - call not sent",
            "prompt_tokens": estimate_tokens(prompt) - 300,
            "completion_tokens": 0,
            "total_tokens": estimate_tokens(prompt) - 300,
            "latency_s": 0.0,
        }

    base = (os.environ.get("FIREWORKS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "obsidia-router/track1-benchmark",
        },
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        # Never log the Authorization header. Include endpoint + model for diagnosis.
        endpoint = f"{base}/chat/completions"
        hint = ""
        if exc.code == 403:
            hint = " (403: check User-Agent/headers or account permissions)"
        elif exc.code == 404:
            hint = " (404: model not available on this account)"
        elif exc.code == 401:
            hint = " (401: invalid or missing FIREWORKS_API_KEY)"
        return {
            "dry_run": False,
            "error": f"HTTP {exc.code}{hint} model={model} endpoint={endpoint}: {detail or exc.reason}",
            "model": model,
            "text": f"[error] Fireworks call failed (HTTP {exc.code}{hint}).",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "latency_s": round(time.perf_counter() - t0, 3),
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "dry_run": False,
            "error": f"network: {exc}",
            "model": model,
            "text": "[error] Fireworks unreachable - network error.",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "latency_s": round(time.perf_counter() - t0, 3),
        }
    latency = time.perf_counter() - t0

    usage = data.get("usage", {})
    choices = data.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}

    content = message.get("content")
    final_content_present = (
        isinstance(content, str) and bool(content.strip())
    )

    reasoning = message.get("reasoning_content")
    reasoning_content_present = (
        isinstance(reasoning, str) and bool(reasoning.strip())
    )

    finish_reason = choice.get("finish_reason")
    completion_tokens = int(
        usage.get("completion_tokens", 0) or 0
    )

    truncated = (
        finish_reason == "length"
        or (
            max_tokens > 0
            and completion_tokens >= max_tokens
        )
    )

    response_error = None
    if not final_content_present:
        response_error = (
            "truncated_before_final_content"
            if truncated
            else "no_final_content"
        )
    elif truncated:
        response_error = "truncated_completion"

    return {
        "dry_run": False,
        "error": response_error,
        "model": model,
        "text": extract_text(data),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": completion_tokens,
        "total_tokens": usage.get("total_tokens", 0),
        "latency_s": round(latency, 3),
        "finish_reason": finish_reason,
        "final_content_present": final_content_present,
        "reasoning_content_present": reasoning_content_present,
        "truncated": truncated,
    }
