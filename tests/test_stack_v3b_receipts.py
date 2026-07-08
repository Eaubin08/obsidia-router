"""Tests — V3B receipts and full stack routing invariants."""
from __future__ import annotations

import os
import pytest

from app.router.decision import decide
from benchmarks.run_benchmark import run_stack_v3b_phase
from benchmarks.stack_families import NO_REMOTE_ROUTES, STACK_V3B_FAMILIES


# ── Receipt field invariants ──────────────────────────────────────────────────

_REQUIRED_RECEIPT_FIELDS = {
    "family", "input_id", "request", "expected_route", "actual_route",
    "route_match", "expected_layer", "actual_level", "bridge_type",
    "model_call_required", "model_call_avoided", "remote_tokens",
    "emits_act", "real_action", "memory_write", "kernel_mutation",
    "decision_authority", "revendicable", "revendicable_reason",
}


def _run_v3b(monkeypatch) -> dict:
    monkeypatch.delenv("BRODY_ENDPOINT", raising=False)
    return run_stack_v3b_phase(require_brody_live=False)


def test_receipts_have_all_required_fields(monkeypatch):
    result = _run_v3b(monkeypatch)
    for row in result["rows"]:
        missing = _REQUIRED_RECEIPT_FIELDS - set(row)
        assert not missing, f"{row['input_id']} missing receipt fields: {missing}"


def test_receipts_governance_invariants(monkeypatch):
    result = _run_v3b(monkeypatch)
    for row in result["rows"]:
        assert row["emits_act"] is False
        assert row["real_action"] is False
        assert row["memory_write"] is False
        assert row["kernel_mutation"] is False
        assert row["decision_authority"] == "KX108_ONLY"


def test_receipts_zero_remote_tokens(monkeypatch):
    result = _run_v3b(monkeypatch)
    for row in result["rows"]:
        assert row["remote_tokens"] == 0, (
            f"{row['input_id']} has non-zero remote_tokens: {row['remote_tokens']}"
        )
    assert result["remote_tokens"] == 0


def test_receipts_model_call_avoided(monkeypatch):
    result = _run_v3b(monkeypatch)
    for row in result["rows"]:
        assert row["model_call_avoided"] is True, (
            f"{row['input_id']} model_call_avoided must be True"
        )


def test_no_fireworks_routes_in_v3b(monkeypatch):
    result = _run_v3b(monkeypatch)
    fireworks_rows = [r for r in result["rows"] if r["actual_route"] == "fireworks"]
    assert not fireworks_rows, (
        f"V3B must not produce fireworks routes: {[r['input_id'] for r in fireworks_rows]}"
    )


# ── Route accuracy local/stub ─────────────────────────────────────────────────

def test_v3b_route_accuracy_100pct_stub(monkeypatch):
    result = _run_v3b(monkeypatch)
    assert result["route_accuracy"] == 1.0, (
        f"V3B route accuracy must be 100% in stub mode, got {result['route_accuracy']:.0%}\n"
        + "\n".join(
            f"  {r['input_id']}: expected={r['expected_route']} actual={r['actual_route']}"
            for r in result["rows"] if not r["route_match"]
        )
    )


# ── Per-family routing (direct router tests) ──────────────────────────────────

@pytest.mark.parametrize("req,expected", [
    ("ping", "no_model_needed"),
    ("status", "no_model_needed"),
    ("health check", "no_model_needed"),
])
def test_fastpath_routes(req, expected):
    d = decide(req)
    assert d["route"] == expected, f"fastpath: {req!r} → {d['route']!r}, expected {expected!r}"


@pytest.mark.parametrize("req", [
    "explique ce qu'est le kernel Obsidia",
    "comment fonctionne le routeur sémantique ?",
])
def test_brody_routes(req):
    d = decide(req)
    assert d["route"] == "brody", f"brody: {req!r} → {d['route']!r}"
    assert d["level"] == 1


@pytest.mark.parametrize("req", [
    "obsidure: génère une proposition de patch pour sigma/contracts.py",
    "obsidure: analyse le fichier app/router/decision.py et propose une amélioration",
])
def test_obsidure_routes(req):
    d = decide(req)
    assert d["route"] == "obsidure_route_only", (
        f"obsidure: {req!r} → {d['route']!r}"
    )
    assert d["level"] == 1


@pytest.mark.parametrize("req", [
    "vérifie l'invariant Lean: forall n : Nat, n + 0 = n",
    "vérifie la preuve merkle du kernel",
])
def test_lean_routes(req):
    d = decide(req)
    assert d["route"] == "lean_route_only", (
        f"lean: {req!r} → {d['route']!r}"
    )
    assert d["level"] == 1


@pytest.mark.parametrize("req", [
    "virement bancaire de 50000 EUR: ALLOW ou HOLD?",
    "transaction bank suspecte montant 120000: ALLOW HOLD ou BLOCK?",
    "signal trading BUY BTC confidence 0.87: VALID ou HOLD_RISK?",
    "trading signal SELL ETH flash crash détecté: VALID ou HOLD_RISK?",
    "terrain signal GPS altitude 950m obstacle clearance 120m: ALLOW ou BLOCK?",
    "aviation route R47 gps spoofing détecté: ALLOW ou BLOCK?",
])
def test_domain_routes(req):
    d = decide(req)
    assert d["route"] == "domain_bridge", (
        f"domain: {req!r} → {d['route']!r}"
    )
    assert d["level"] == 1


# ── obsidure/lean/domain never consume Fireworks tokens ──────────────────────

def test_stack_routes_no_fireworks():
    for case in STACK_V3B_FAMILIES:
        if case["family"] in ("obsidure_proposal", "lean_proof_query",
                              "domain_bank", "domain_trading", "domain_gps"):
            d = decide(case["request"])
            assert d["route"] != "fireworks", (
                f"{case['input_id']} routed to fireworks: {d['route']!r}"
            )
            assert d["model"] is None, (
                f"{case['input_id']} has non-None model: {d['model']!r}"
            )


# ── Brody mode without endpoint → stub ───────────────────────────────────────

def test_brody_stub_without_endpoint(monkeypatch):
    monkeypatch.delenv("BRODY_ENDPOINT", raising=False)
    result = run_stack_v3b_phase(require_brody_live=False)
    assert result["brody_status"] == "stub"
    assert result["brody_live_ok"] is True


def test_require_brody_live_fails_without_endpoint(monkeypatch):
    monkeypatch.delenv("BRODY_ENDPOINT", raising=False)
    result = run_stack_v3b_phase(require_brody_live=True)
    assert result["brody_live_ok"] is False
    assert result["brody_status"] == "REQUIRED_BUT_MISSING"
