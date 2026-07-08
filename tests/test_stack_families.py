"""Tests — V3B stack families registry."""
from __future__ import annotations

import pytest

from benchmarks.stack_families import (
    NO_REMOTE_ROUTES,
    STACK_V3B_FAMILIES,
    V3B_FAMILY_NAMES,
)

_REQUIRED_FIELDS = {
    "family", "input_id", "request", "expected_route", "expected_layer",
    "bridge_type", "model_call_required", "model_call_avoided",
    "real_action", "memory_write", "kernel_mutation", "emits_act",
    "decision_authority", "revendicable", "revendicable_reason",
}


def test_all_families_have_required_fields():
    for case in STACK_V3B_FAMILIES:
        missing = _REQUIRED_FIELDS - set(case)
        assert not missing, f"{case['input_id']} missing fields: {missing}"


def test_all_invariants_false():
    for case in STACK_V3B_FAMILIES:
        assert case["real_action"] is False, f"{case['input_id']} real_action must be False"
        assert case["memory_write"] is False, f"{case['input_id']} memory_write must be False"
        assert case["kernel_mutation"] is False, f"{case['input_id']} kernel_mutation must be False"
        assert case["emits_act"] is False, f"{case['input_id']} emits_act must be False"


def test_decision_authority_kx108():
    for case in STACK_V3B_FAMILIES:
        assert case["decision_authority"] == "KX108_ONLY", (
            f"{case['input_id']} decision_authority must be KX108_ONLY"
        )


def test_expected_routes_are_no_remote():
    for case in STACK_V3B_FAMILIES:
        assert case["expected_route"] in NO_REMOTE_ROUTES, (
            f"{case['input_id']} expected_route {case['expected_route']!r} "
            f"not in NO_REMOTE_ROUTES"
        )


def test_model_call_avoided_true():
    for case in STACK_V3B_FAMILIES:
        assert case["model_call_avoided"] is True, (
            f"{case['input_id']} model_call_avoided must be True"
        )


def test_model_call_required_false():
    for case in STACK_V3B_FAMILIES:
        assert case["model_call_required"] is False, (
            f"{case['input_id']} model_call_required must be False"
        )


def test_all_v3b_family_names_present():
    present = {c["family"] for c in STACK_V3B_FAMILIES}
    for name in V3B_FAMILY_NAMES:
        assert name in present, f"V3B family {name!r} has no fixtures"


def test_unique_input_ids():
    ids = [c["input_id"] for c in STACK_V3B_FAMILIES]
    assert len(ids) == len(set(ids)), "Duplicate input_id values in STACK_V3B_FAMILIES"


def test_no_remote_routes_does_not_include_fireworks():
    assert "fireworks" not in NO_REMOTE_ROUTES
    assert "denied" not in NO_REMOTE_ROUTES


def test_fastpath_route():
    fp = [c for c in STACK_V3B_FAMILIES if c["family"] == "fastpath_structured"]
    assert fp, "No fastpath_structured cases"
    for case in fp:
        assert case["expected_route"] == "no_model_needed"
        assert case["expected_layer"] == "FAST_PATH"
        assert case["bridge_type"] == "DIRECT_ROUTE"


def test_brody_route():
    br = [c for c in STACK_V3B_FAMILIES if c["family"] == "brody_readonly"]
    assert br
    for case in br:
        assert case["expected_route"] == "brody"
        assert case["bridge_type"] == "BRODY_READONLY"


def test_obsidure_route():
    ob = [c for c in STACK_V3B_FAMILIES if c["family"] == "obsidure_proposal"]
    assert ob
    for case in ob:
        assert case["expected_route"] == "obsidure_route_only"
        assert case["bridge_type"] == "OBSIDURE_PROPOSAL_READONLY"


def test_lean_route():
    ln = [c for c in STACK_V3B_FAMILIES if c["family"] == "lean_proof_query"]
    assert ln
    for case in ln:
        assert case["expected_route"] == "lean_route_only"
        assert case["bridge_type"] == "LEAN_PROOF_CHECK"


def test_domain_routes():
    for fam, bridge in [
        ("domain_bank", "DOMAIN_BANK"),
        ("domain_trading", "DOMAIN_TRADING"),
        ("domain_gps", "DOMAIN_GPS"),
    ]:
        cases = [c for c in STACK_V3B_FAMILIES if c["family"] == fam]
        assert cases, f"No cases for {fam}"
        for case in cases:
            assert case["expected_route"] == "domain_bridge"
            assert case["bridge_type"] == bridge
