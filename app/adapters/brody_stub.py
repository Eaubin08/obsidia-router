"""Brody — local proprietary LLM organ (public stub).

In the full Obsidia stack, Brody is the in-house LLM organ that receives an
ALREADY-STRUCTURED request (IR + topic + constraints) and links it to memory.
The proprietary weights and memory stay out of this public cut; this stub
keeps the interface and the contract so the routing level is demonstrable.

Contract: Brody never receives raw language. It receives the compiled frame.
"""
from __future__ import annotations


def answer(ir: dict, topic: dict) -> dict:
    """Bounded local answer built from the structured frame."""
    text = (
        f"[brody-stub] topic={topic['topic']} intent={ir['intent_type']} "
        f"layer={ir['target_layer']} — bounded local answer. "
        "In the full stack, Brody links this frame to memory and produces "
        "the semantic answer without any remote call."
    )
    return {"organ": "brody", "text": text, "remote_tokens": 0}
