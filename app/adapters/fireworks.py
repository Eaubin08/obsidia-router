"""Fireworks AI adapter — the ONLY place where remote tokens are spent.

OpenAI-compatible chat completion over the Fireworks API. Stdlib only.

Environment:
  FIREWORKS_API_KEY   required for live calls; without it the adapter runs
                      in dry-run mode (decision + estimate, no network)
  FIREWORKS_BASE_URL  default https://api.fireworks.ai/inference/v1
  ALLOWED_MODELS      optional comma-separated ladder, cheapest first;
                      overrides the default ladder for scoring harnesses
"""
from __future__ import annotations

import json
import os
import time
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
        },
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    latency = time.perf_counter() - t0

    usage = data.get("usage", {})
    return {
        "dry_run": False,
        "model": model,
        "text": data["choices"][0]["message"]["content"],
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "latency_s": round(latency, 3),
    }
