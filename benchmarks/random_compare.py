"""Random comparative phase: Obsidia Router vs raw LLM.

This is the live behavioral comparison for replayable random prompts.
The same generated dirty prompt is evaluated by:
1) Obsidia Router: IR -> gate -> level -> route
2) Raw LLM baseline: prompt sent directly to Fireworks

The goal is not to prove that Obsidia is a smarter model. The goal is to
measure inference avoidance, frame stability, latency and raw-model behavior
on the same stochastic sample.
"""

from __future__ import annotations

from typing import Any

GOVERNED_RANDOM_FAMILIES = {
    "dirty_world_action",
    "masked_destructive",
    "ultra_short_ambiguous",
}


def flatten_cases(plan: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Flatten generated random batches into a stable sample."""

    out: list[dict[str, Any]] = []
    for batch in plan["batches"]:
        for case in batch["cases"]:
            out.append(case)
            if len(out) >= limit:
                return out
    return out


def is_governed_random_case(case: dict[str, Any]) -> bool:
    """Cases where raw behavior can be scored for frame violations."""

    return case.get("family") in GOVERNED_RANDOM_FAMILIES


def raw_answer_text(response: dict[str, Any]) -> str:
    """Extract answer text from possible Fireworks adapter shapes."""

    for key in ("answer", "content", "text", "output"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value

    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content
            text = first.get("text")
            if isinstance(text, str) and text.strip():
                return text

    return ""



def raw_case_verdict(case: dict[str, Any], raw_score: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize raw LLM frame score for one random case."""

    if not is_governed_random_case(case):
        return {
            "scored": False,
            "violation": None,
            "reason": "not governed random family",
        }

    if raw_score is None:
        return {
            "scored": False,
            "violation": None,
            "reason": "raw answer not captured",
        }

    return {
        "scored": True,
        "violation": bool(raw_score.get("violation")),
        "reason": raw_score.get("reason", "n/a"),
    }
