"""Fireworks AI adapter — the ONLY place where remote tokens are spent.

OpenAI-compatible chat completion over the Fireworks API. Stdlib only.

Environment:
  FIREWORKS_API_KEY   required for live calls; without it the adapter runs
                      in dry-run mode (decision + estimate, no network)
  FIREWORKS_BASE_URL  default https://api.fireworks.ai/inference/v1
  ALLOWED_MODELS      optional comma-separated ladder, cheapest first;
                      overrides the default ladder for scoring harnesses

Headers sent on every request:
  Authorization: Bearer <key>
  Content-Type: application/json
  Accept: application/json
  User-Agent: obsidia-router/track1-benchmark
  (Cloudflare blocks Python-urllib default UA with 403/1010 — explicit UA required)
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.fireworks.ai/inference/v1"


def allowed_models() -> list[str] | None:
    raw = os.environ.get("ALLOWED_MODELS", "").strip()
    if not raw:
        return None
    return [m.strip() for m in raw.split(",") if m.strip()]


def estimate_tokens(text: str) -> int:
    """Deterministic estimate used for 'tokens saved' accounting: ~4 chars/token
    plus a typical bounded completion."""
    return len(text) // 4 + 300


def extract_text(data: dict) -> str:
    """Tolerant extraction of the answer text from an OpenAI-compatible
    response. Reasoning models (e.g. gpt-oss) may return reasoning_content,
    a null content, or hit the max_tokens cap mid-reasoning."""
    choices = data.get("choices") or []
    if not choices:
        return "[error] no choices in response"
    msg = choices[0].get("message") or {}
    return (msg.get("content")
            or msg.get("reasoning_content")
            or "[empty completion]")


def chat(model: str, prompt: str, max_tokens: int = 512,
         system: str | None = None, timeout: float = 60.0) -> dict:
    """One chat completion. Returns text + real token usage, or a dry-run
    record when no API key is configured."""
    api_key = os.environ.get("FIREWORKS_API_KEY", "").strip()
    if not api_key:
        return {
            "dry_run": True,
            "model": model,
            "text": "[dry-run] no FIREWORKS_API_KEY — call not sent",
            "prompt_tokens": estimate_tokens(prompt) - 300,
            "completion_tokens": 0,
            "total_tokens": estimate_tokens(prompt) - 300,
            "latency_s": 0.0,
        }

    base = os.environ.get("FIREWORKS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
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
            "text": "[error] Fireworks unreachable — network error.",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "latency_s": round(time.perf_counter() - t0, 3),
        }
    latency = time.perf_counter() - t0

    usage = data.get("usage", {})
    return {
        "dry_run": False,
        "model": model,
        "text": extract_text(data),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "latency_s": round(latency, 3),
    }
