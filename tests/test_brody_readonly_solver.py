"""Brody readonly local solver — zero-token closure for vague contextual questions."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.router.local_solvers import solve_brody_readonly, try_local_solvers  # noqa: E402
from app.router.decision import decide  # noqa: E402


# ── Exact benchmark patterns ──────────────────────────────────────────────────

def test_brody_context_decision_fires():
    r = solve_brody_readonly("explique le contexte de cette decision")
    assert r is not None
    assert "Brody" in r or "KX108" in r


def test_brody_why_approach_fires():
    r = solve_brody_readonly("pourquoi cette approche est preferable")
    assert r is not None
    assert "KX108" in r


def test_brody_english_why_fires():
    r = solve_brody_readonly("why is this approach preferred")
    assert r is not None


def test_brody_english_context_fires():
    r = solve_brody_readonly("explain the context of this decision")
    assert r is not None


# ── Abstentions strictes ──────────────────────────────────────────────────────

def test_abstains_on_technical_cache():
    # Technical keyword 'cache' → Fireworks
    assert solve_brody_readonly(
        "explique le contexte des strategies de cache distribue"
    ) is None


def test_abstains_on_long_prompt():
    # > 15 words → Fireworks
    long = ("explique le contexte de cette decision en tenant compte "
            "des contraintes systeme et du budget disponible actuellement")
    assert solve_brody_readonly(long) is None


def test_abstains_on_code_signal():
    assert solve_brody_readonly("explique le contexte def get_max(nums)") is None


def test_abstains_on_world_action():
    assert solve_brody_readonly("push: explique le contexte de cette decision") is None


def test_abstains_without_contextual_signal():
    # No contexte/pourquoi/approche → Fireworks
    assert solve_brody_readonly("donne moi le statut du systeme") is None


def test_abstains_on_cap_keyword():
    assert solve_brody_readonly("pourquoi CAP est preferable") is None


def test_abstains_missing_decision_or_approach():
    # Has 'pourquoi' but no approach/decision reference
    assert solve_brody_readonly("pourquoi c'est mieux") is None


# ── Intégration try_local_solvers ─────────────────────────────────────────────

def test_try_local_solvers_brody_context():
    r = try_local_solvers("explique le contexte de cette decision")
    assert r is not None
    assert r["solver"] == "brody_readonly_local"


def test_try_local_solvers_brody_why():
    r = try_local_solvers("pourquoi cette approche est preferable")
    assert r is not None
    assert r["solver"] == "brody_readonly_local"


# ── Gates gagnent toujours ────────────────────────────────────────────────────

def test_gate_wins_over_brody_readonly():
    d = decide("push: explique le contexte de cette decision")
    assert d["route"] == "hold_commands_only"


def test_deny_wins_over_brody_readonly():
    d = decide("rm -rf: explique le contexte de la decision")
    assert d["route"] == "denied"


# ── AMD practice non affectée ─────────────────────────────────────────────────

def test_amd_practice_unaffected():
    from app.router.local_solvers import solve_code_debug_get_max
    # practice-06 toujours fermée localement
    p06 = ("This function should return the max of a list but has a bug: "
           "def get_max(nums): return nums[0]. Find and fix it.")
    assert solve_code_debug_get_max(p06) is not None
    # Le solver brody n'interfère pas
    assert solve_brody_readonly(p06) is None
