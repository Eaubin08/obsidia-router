"""Qwen local adapter — stdlib-only HTTP to llama-server on loopback.

Only connects to 127.0.0.1 / localhost / ::1.  Never uses FIREWORKS_API_KEY.
Never projects reasoning chains.  Returns a provider-tagged dict compatible
with the existing validate_remote_output / repair_remote_output pipeline.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

# ── Loopback-only enforcement ─────────────────────────────────────────────────

_ALLOWED_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})

# ── Per-family token budgets ──────────────────────────────────────────────────

_MAX_TOKENS_BY_KIND: dict[str, int] = {
    "sentiment": 8,
    "factual":   32,
    "summary":   96,
    "ner":       64,
    "math":      48,
    "logic":     64,
    "code_debug": 128,
    "code_gen":  128,
    # contract answer_kind values
    "direct_answer":      48,
    "structured_summary": 96,
    "comparison":        128,
    "code_file":         256,
    "clarification":      32,
}
_DEFAULT_MAX_TOKENS = 48
_DEFAULT_TIMEOUT_S  = 20.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_endpoint() -> str:
    return os.environ.get(
        "QWEN_LOCAL_ENDPOINT", "http://127.0.0.1:8080/v1"
    ).rstrip("/")


def _validate_loopback(endpoint: str) -> None:
    host = urlparse(endpoint).hostname or ""
    if host not in _ALLOWED_HOSTS:
        raise ValueError(
            f"qwen_local: endpoint host {host!r} is not loopback — "
            "rejected for zero-remote-token safety"
        )


def _detect_category(prompt: str) -> str:
    """Heuristic category detection from prompt text (never from task_id)."""
    p = prompt.lower()
    if re.search(
        r"\b(positive|negative|neutral)\b.{0,80}\b(positive|negative|neutral)\b",
        p, re.S
    ):
        return "sentiment"
    if re.search(r"\bsummar(?:ize|ise|y)\b|\bone-sentence summary\b", p):
        return "summary"
    if re.search(
        r"\bextract\b.{0,60}\b(email|url|entit|named\s+entit|name|"
        r"organization|person|location|date)\b", p
    ):
        return "ner"
    if re.search(r"\bfix\b.{0,40}\bbug\b|\bdebug\b|\bfind.*bug\b", p):
        return "code_debug"
    if re.search(r"\bwrite\b.{0,30}\bpython\b|\bpython\s+function\b", p):
        return "code_gen"
    if re.search(r"\b(calculate|compute|\d+\s*[+\-*/]\s*\d+|percent|average|speed)\b", p):
        return "math"
    return "factual"


def _system_prompt(category: str) -> str:
    if category == "sentiment":
        return (
            "Classify the sentiment. "
            "Reply with exactly one word: positive, negative, or neutral. "
            "No other words."
        )
    if category == "summary":
        return (
            "Summarize in exactly one sentence. "
            "Output only that sentence, nothing else."
        )
    if category == "ner":
        return "Extract the requested named entities. Be brief and direct."
    if category == "code_debug":
        return "Fix the bug. Show corrected code only. No explanation."
    if category == "code_gen":
        return (
            "Write the requested Python function. "
            "Output code only, starting with def. No explanation."
        )
    if category == "math":
        return "Answer with only the numeric result. No explanation."
    # default: factual
    return (
        "Answer the exact entity requested. "
        "For a capital question, return the capital city name only — "
        "never the country, region, state, nearby city or containing metropolitan area. "
        "When a short or one-word answer is requested, output only the city name. "
        "Do not add explanations unless explicitly requested."
    )


# ── Public API ────────────────────────────────────────────────────────────────

def chat(
    prompt: str,
    answer_kind: str = "",
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> dict:
    """Call llama-server OpenAI-compatible API.

    Returns:
        {
            "text":              str,       # answer text (stripped)
            "success":           bool,
            "status":            str,       # ok | timeout | invalid_response | not_available
            "error":             str|None,
            "elapsed_ms":        float,
            "provider":          "qwen_local",
            "local_model_tokens": int|None, # completion tokens if reported by server
        }

    Tokens here are LOCAL inference tokens, never Fireworks tokens.
    """
    t0 = time.perf_counter()

    endpoint = _get_endpoint()
    try:
        _validate_loopback(endpoint)
    except ValueError as exc:
        return _err("not_available", str(exc), t0)

    category = _detect_category(prompt)
    max_tok = (
        _MAX_TOKENS_BY_KIND.get(answer_kind)
        or _MAX_TOKENS_BY_KIND.get(category, _DEFAULT_MAX_TOKENS)
    )
    system = _system_prompt(category)

    body = json.dumps({
        "model": "qwen",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": max_tok,
        "temperature": 0.0,
        "stream": False,
    }).encode("utf-8")

    url = f"{endpoint}/chat/completions"
    req = urllib.request.Request(
        url, data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        status = (
            "timeout" if "timed out" in str(exc).lower() else "not_available"
        )
        return _err(status, str(exc), t0)
    except Exception as exc:
        return _err("invalid_response", str(exc), t0)

    elapsed = (time.perf_counter() - t0) * 1000

    try:
        choices = data.get("choices") or []
        if not choices:
            return _err("invalid_response", "no choices in response", t0)
        message = choices[0].get("message") or {}
        content = (message.get("content") or "").strip()
        if not content:
            return _err("invalid_response", "empty content in response", t0)

        usage = data.get("usage") or {}
        local_tokens = (
            usage.get("completion_tokens")
            or usage.get("total_tokens")
        )
        return {
            "text": content,
            "success": True,
            "status": "ok",
            "error": None,
            "elapsed_ms": round(elapsed, 1),
            "provider": "qwen_local",
            "local_model_tokens": local_tokens,
        }
    except Exception as exc:
        return _err("invalid_response", f"parse error: {exc}", t0)


def _err(status: str, error: str, t0: float) -> dict:
    return {
        "text": "",
        "success": False,
        "status": status,
        "error": error,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        "provider": "qwen_local",
        "local_model_tokens": None,
    }


def is_available(timeout: float = 2.0) -> bool:
    """Quick health check — returns True only when llama-server is reachable."""
    endpoint = _get_endpoint()
    try:
        _validate_loopback(endpoint)
        parsed = urlparse(endpoint)
        health = f"{parsed.scheme}://{parsed.netloc}/health"
        with urllib.request.urlopen(health, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False
