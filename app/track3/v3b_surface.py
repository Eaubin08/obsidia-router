"""Track 3 V3B route surface — maps stack_families to T3 capability statuses.

The V3B families describe the governed routing layers of Obsidia.
In Track 3, only some layers are actually wired; the rest are route_only.

Bridge type → T3 status:
  DIRECT_ROUTE              → available      (no model needed)
  BRODY_READONLY            → conditional    (BRODY_ENDPOINT required)
  OBSIDURE_PROPOSAL_READONLY → route_only    (Obsidure not wired in T3)
  LEAN_PROOF_CHECK          → route_only     (Lean in separate repo)
  DOMAIN_BANK               → route_only     (private connectors)
  DOMAIN_TRADING            → route_only     (private connectors)
  DOMAIN_GPS                → route_only     (private connectors)

Invariant: executed = False for all route_only entries.
decision_authority = KX108_ONLY on every entry.
"""
from __future__ import annotations

from benchmarks.stack_families import STACK_V3B_FAMILIES

_BRIDGE_TO_T3_STATUS: dict[str, str] = {
    "DIRECT_ROUTE":                "available",
    "BRODY_READONLY":              "conditional",
    "OBSIDURE_PROPOSAL_READONLY":  "route_only",
    "LEAN_PROOF_CHECK":            "route_only",
    "DOMAIN_BANK":                 "route_only",
    "DOMAIN_TRADING":              "route_only",
    "DOMAIN_GPS":                  "route_only",
}

_BRIDGE_EXECUTED: dict[str, bool | None] = {
    "DIRECT_ROUTE":                None,        # depends on input
    "BRODY_READONLY":              None,        # depends on BRODY_ENDPOINT
    "OBSIDURE_PROPOSAL_READONLY":  False,       # never
    "LEAN_PROOF_CHECK":            False,       # never
    "DOMAIN_BANK":                 False,       # never
    "DOMAIN_TRADING":              False,       # never
    "DOMAIN_GPS":                  False,       # never
}


def get_v3b_route_statuses() -> list[dict]:
    """Return one descriptor per unique bridge_type in the V3B registry.

    Returns list of:
        {
            "family":           str,
            "expected_route":   str,
            "bridge_type":      str,
            "t3_status":        "available" | "conditional" | "route_only",
            "executed":         bool | None,
            "decision_authority": "KX108_ONLY",
        }
    """
    seen: set[str] = set()
    statuses: list[dict] = []

    for fam in STACK_V3B_FAMILIES:
        bt = fam.get("bridge_type", "UNKNOWN")
        if bt in seen:
            continue
        seen.add(bt)

        t3_status = _BRIDGE_TO_T3_STATUS.get(bt, "unknown")
        executed  = _BRIDGE_EXECUTED.get(bt, None)

        statuses.append({
            "family":             fam.get("family", ""),
            "expected_route":     fam.get("expected_route", ""),
            "bridge_type":        bt,
            "t3_status":          t3_status,
            "executed":           executed,
            "decision_authority": "KX108_ONLY",
        })

    return statuses


def get_unavailable_v3b_routes() -> list[dict]:
    """Return V3B routes that are route_only (never executed) in T3."""
    return [r for r in get_v3b_route_statuses() if r["t3_status"] == "route_only"]


def get_unique_route_families() -> list[str]:
    """Return the list of unique expected_route values in the V3B registry."""
    return sorted({fam.get("expected_route", "") for fam in STACK_V3B_FAMILIES})
