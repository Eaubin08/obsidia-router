"""Probe every rung of the model ladder with one minimal live call each.

Proves each model in ALLOWED_MODELS (or the default ladder) is reachable:
- the Fireworks API key works
- the model accepts a call
- a non-truncated content token returns
- token counts are measurable

PASS criteria per rung:
  - API call succeeds (no transport error)
  - final_content_present is True OR text is non-empty and not a dry-run marker
  - text (normalised) starts with or contains "OK"
  - finish_reason is NOT "length" / truncated
  - total_tokens is present and > 0

FAIL criteria per rung:
  - transport error
  - no final content
  - truncated completion (finish_reason=length)
  - empty or dry-run text
  - text does not contain OK

Usage (spends a few tokens per rung):
    FIREWORKS_API_KEY=... python benchmarks/probe_ladder.py
    ALLOWED_MODELS="modelA,modelB" FIREWORKS_API_KEY=... python benchmarks/probe_ladder.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.adapters import fireworks
from app.router.decision import DEFAULT_MODEL_LADDER

# ── Probe spec ────────────────────────────────────────────────────────────────
# Minimal, deterministic, no reasoning required.
# System instruction explicitly requests one-word output to avoid model
# verbosity and reasoning preamble.
_PROBE_SYSTEM = "You are a connectivity probe. Output exactly OK and nothing else."
_PROBE_PROMPT = "Return exactly OK."
_PROBE_MAX_TOKENS = 64   # enough for any reasoning overhead + "OK"


def _probe_rung(model: str) -> dict:
    """Fire one minimal call and return a structured probe result."""
    r = fireworks.chat(
        model,
        _PROBE_PROMPT,
        max_tokens=_PROBE_MAX_TOKENS,
        system=_PROBE_SYSTEM,
    )
    text_raw = r.get("text") or ""
    text_norm = text_raw.strip().upper()
    dry_run = bool(r.get("dry_run"))

    if dry_run:
        return {
            "status": "DRY_RUN",
            "pass": False,
            "reason": "no FIREWORKS_API_KEY — call not sent",
            "model": model,
            "actual_model": "-",
            "finish_reason": "-",
            "prompt_tokens": r.get("prompt_tokens", 0),
            "completion_tokens": r.get("completion_tokens", 0),
            "total_tokens": r.get("total_tokens", 0),
            "text": text_raw[:60],
        }

    error = r.get("error")
    truncated = r.get("truncated", False)
    finish_reason = r.get("finish_reason") or "-"
    final_content = r.get("final_content_present", True)
    total_tokens = r.get("total_tokens", 0)

    # Evaluate PASS conditions
    if error:
        status, reason = "FAIL", f"error: {error}"
    elif not final_content:
        status, reason = "FAIL", "no final content returned"
    elif truncated or finish_reason == "length":
        status, reason = "FAIL", f"completion truncated (finish_reason={finish_reason})"
    elif not text_norm:
        status, reason = "FAIL", "empty response text"
    elif "OK" not in text_norm:
        status, reason = "FAIL", f"response does not contain OK: {text_raw[:60]!r}"
    elif total_tokens == 0:
        status, reason = "FAIL", "total_tokens=0 (token counting broken)"
    else:
        status, reason = "PASS", "connectivity confirmed"

    return {
        "status": status,
        "pass": status == "PASS",
        "reason": reason,
        "model": model,
        "actual_model": r.get("model", "-") or "-",
        "finish_reason": finish_reason,
        "prompt_tokens": r.get("prompt_tokens", 0),
        "completion_tokens": r.get("completion_tokens", 0),
        "total_tokens": total_tokens,
        "text": text_raw[:60].replace("\n", " "),
    }


def main() -> int:
    ladder = fireworks.allowed_models() or DEFAULT_MODEL_LADDER
    print(f"LADDER PROBE — {len(ladder)} rung(s)")
    print(f"{'rung':<5} {'requested_model':<30} {'actual_model':<24} "
          f"{'status':<8} {'finish':<10} {'p_tok':>6} {'c_tok':>6} "
          f"{'total':>6} reason")
    print("-" * 120)

    failures = 0
    dry_runs = 0
    results = []
    for i, model in enumerate(ladder):
        res = _probe_rung(model)
        results.append(res)
        short_name = model.split("/")[-1]
        actual = res["actual_model"].split("/")[-1] if "/" in res["actual_model"] else res["actual_model"]
        print(
            f"  {i:<4} {short_name:<30} {actual:<24} "
            f"{res['status']:<8} {res['finish_reason']:<10} "
            f"{res['prompt_tokens']:>6} {res['completion_tokens']:>6} "
            f"{res['total_tokens']:>6}  {res['reason']}"
        )
        if res["status"] == "DRY_RUN":
            dry_runs += 1
        elif not res["pass"]:
            failures += 1

    print()
    if dry_runs == len(ladder):
        verdict = "DRY_RUN — set FIREWORKS_API_KEY to run live probe"
    elif failures == 0:
        verdict = "ALL_RUNGS_LIVE"
    else:
        verdict = f"{failures} rung(s) not proven"
    print(f"result: {verdict}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
