"""Bounded capability registry for the Track 3 runtime.

Only capabilities that are ACTUALLY wired in this deployment are listed as
available. Private / unconnected layers appear in UNAVAILABLE_CAPABILITIES
with an explicit reason — they may never be declared as executed.
"""
from __future__ import annotations

_CAPABILITY_REGISTRY: dict[str, dict] = {
    "structural_answer": {
        "capability_id": "structural_answer",
        "description": "Answer derived from IR structure — no inference",
        "input_requirements": ["intent_type in {status, plan, brody_readonly}"],
        "execution_class": "deterministic",
        "locality": "local",
        "mutating": False,
        "availability": "available",
        "reason_for_selection": "intent resolved by structural inspection",
    },
    "deterministic_math": {
        "capability_id": "deterministic_math",
        "description": "Arithmetic, percentages, rate problems via pattern-matching",
        "input_requirements": ["numeric expression or rate problem in prompt"],
        "execution_class": "deterministic",
        "locality": "local",
        "mutating": False,
        "availability": "available",
        "reason_for_selection": "math pattern matched by local solver",
    },
    "deterministic_factual": {
        "capability_id": "deterministic_factual",
        "description": "Canonical geographic / factual answers from local fact_resolver",
        "input_requirements": ["factual question with known canonical answer"],
        "execution_class": "deterministic",
        "locality": "local",
        "mutating": False,
        "availability": "available",
        "reason_for_selection": "fact resolved by local fact_resolver",
    },
    "deterministic_sentiment": {
        "capability_id": "deterministic_sentiment",
        "description": "Sentiment classification via lexical rule engine",
        "input_requirements": ["sentiment trigger in prompt"],
        "execution_class": "deterministic",
        "locality": "local",
        "mutating": False,
        "availability": "available",
        "reason_for_selection": "sentiment trigger matched",
    },
    "deterministic_ner": {
        "capability_id": "deterministic_ner",
        "description": "Named entity recognition via rule engine",
        "input_requirements": ["NER trigger and target sentence in prompt"],
        "execution_class": "deterministic",
        "locality": "local",
        "mutating": False,
        "availability": "available",
        "reason_for_selection": "NER trigger matched",
    },
    "deterministic_code": {
        "capability_id": "deterministic_code",
        "description": "Code generation / debug via fingerprint-gated template engine",
        "input_requirements": ["code request matching a known fingerprint"],
        "execution_class": "deterministic",
        "locality": "local",
        "mutating": False,
        "availability": "available",
        "reason_for_selection": "code fingerprint matched by local solver",
    },
    "local_qwen": {
        "capability_id": "local_qwen",
        "description": "Open question answered by Qwen2.5-3B via llama-server on loopback",
        "input_requirements": ["llama-server running on 127.0.0.1:8080"],
        "execution_class": "model_local",
        "locality": "local",
        "mutating": False,
        "availability": "conditional",
        "reason_for_selection": "no deterministic solver matched; local model used",
    },
    "clarify": {
        "capability_id": "clarify",
        "description": "Return bounded clarification request — no model invoked",
        "input_requirements": ["unknown or incomplete intent"],
        "execution_class": "deterministic",
        "locality": "local",
        "mutating": False,
        "availability": "available",
        "reason_for_selection": "intent not deterministically resolvable",
    },
    "hold": {
        "capability_id": "hold",
        "description": "Gate holds world action — commands-only, never auto-executed",
        "input_requirements": ["world_action intent or HOLD keyword in gate"],
        "execution_class": "deterministic",
        "locality": "local",
        "mutating": False,
        "availability": "available",
        "reason_for_selection": "world action keyword matched by gate",
    },
    "deny": {
        "capability_id": "deny",
        "description": "Gate blocks destructive or out-of-frame request",
        "input_requirements": ["DENY keyword in gate"],
        "execution_class": "deterministic",
        "locality": "local",
        "mutating": False,
        "availability": "available",
        "reason_for_selection": "destructive keyword matched by gate",
    },
}

UNAVAILABLE_CAPABILITIES: dict[str, str] = {
    "brody":          "engine not connected — brody_stub only; real Brody is private",
    "obsidure":       "engine not connected — route-only tag in public deployment",
    "lean":           "Lean 4 in separate repo (obsidia-x108-proofs) — not wired to router",
    "sigma":          "Sigma layer not wired to router in public deployment",
    "oie":            "OIE layer not available in public deployment",
    "domain_bridges": "Aviation/bank/trading connectors in private deployment only",
    "fireworks":      "Fireworks.ai adapter disabled in Track 3 runtime — zero remote tokens",
}


def list_available() -> dict:
    return dict(_CAPABILITY_REGISTRY)


def get(capability_id: str) -> dict | None:
    return _CAPABILITY_REGISTRY.get(capability_id)


def is_available(capability_id: str) -> bool:
    return capability_id in _CAPABILITY_REGISTRY


def select(plan: dict, gate_verdict: dict) -> tuple[str, dict]:
    """Select the best capability given the active plan and gate verdict.

    Returns (capability_id, capability_info).
    Never returns an UNAVAILABLE capability.
    Always honours gate DENY/HOLD/CLARIFY before plan requirements.
    """
    verdict = gate_verdict["verdict"]

    if verdict == "DENY":
        cap = dict(_CAPABILITY_REGISTRY["deny"])
        cap["reason_for_selection"] = gate_verdict["reason"]
        return "deny", cap

    if verdict == "HOLD":
        cap = dict(_CAPABILITY_REGISTRY["hold"])
        cap["reason_for_selection"] = gate_verdict["reason"]
        return "hold", cap

    if verdict == "CLARIFY":
        cap = dict(_CAPABILITY_REGISTRY["clarify"])
        cap["reason_for_selection"] = gate_verdict["reason"]
        return "clarify", cap

    # ALLOW — iterate plan requirements, skip unavailable / gate-only capabilities
    _gate_only = {"hold", "deny", "clarify"}
    for cap_id in plan.get("required_capabilities", []):
        if cap_id in _CAPABILITY_REGISTRY and cap_id not in _gate_only:
            cap = dict(_CAPABILITY_REGISTRY[cap_id])
            cap["reason_for_selection"] = "first matching capability from active plan"
            return cap_id, cap

    # Final fallback: structural if allowed
    cap = dict(_CAPABILITY_REGISTRY["structural_answer"])
    cap["reason_for_selection"] = "fallback — no plan capability matched"
    return "structural_answer", cap


def describe_unavailable() -> list[dict]:
    return [
        {"capability_id": k, "status": "unavailable", "reason": v}
        for k, v in UNAVAILABLE_CAPABILITIES.items()
    ]
