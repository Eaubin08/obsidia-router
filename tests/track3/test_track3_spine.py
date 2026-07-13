"""Track 3 spine tests — Cases A through E.

No Fireworks calls. No network calls. No real subprocess.
Qwen tests are skipped cleanly when llama-server is unavailable.
"""
from __future__ import annotations

import pytest

from app.track3 import runtime
from app.track3 import receipt as receipt_mod
from app.track3 import capability_resolver


# ── Case A — Local deterministic closure ────────────────────────────────────
# A deterministic local solver closes the request: no model, no external call.

class TestCaseA_LocalClosure:
    def test_math_closed_locally(self):
        ev = runtime.run("What is 12 * 78?", qwen_available=False)
        assert ev["status"] == "resolved"
        assert ev["answer"] == "936"
        assert ev["model_invoked"] is None
        assert ev["external_calls"] == []
        assert ev["decision_authority"] == "KX108_ONLY"
        assert ev["receipt_hash"] != ""

    def test_math_percent_closed_locally(self):
        ev = runtime.run("What is 15% of 200?", qwen_available=False)
        assert ev["status"] == "resolved"
        assert ev["answer"] == "30"
        assert ev["model_invoked"] is None
        assert ev["external_calls"] == []

    def test_sentiment_closed_locally(self):
        ev = runtime.run(
            "Classify the sentiment: The movie was great and I loved every moment of it.",
            qwen_available=False,
        )
        assert ev["status"] == "resolved"
        assert "positive" in ev["answer"].lower()
        assert ev["model_invoked"] is None
        assert ev["external_calls"] == []
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_local_closure_receipt_valid(self):
        ev = runtime.run("What is 7 * 8?", qwen_available=False)
        assert ev["status"] == "resolved"
        assert receipt_mod.verify_hash(ev), "receipt_hash does not match payload"

    def test_local_closure_no_mutations(self):
        ev = runtime.run("What is 100 + 200?", qwen_available=False)
        assert ev["mutations_performed"] == []

    def test_local_closure_kx108_only(self):
        ev = runtime.run("What is 5 + 3?", qwen_available=False)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_local_closure_organ_invoked(self):
        ev = runtime.run("What is 2 * 2?", qwen_available=False)
        assert ev["organ_invoked"] is not None, "organ_invoked must name the local solver"

    def test_capability_selected_is_deterministic(self):
        ev = runtime.run("What is 10 * 10?", qwen_available=False)
        cap_id = ev["capability_selected"].get("capability_id", "")
        assert cap_id in (
            "deterministic_math",
            "deterministic_factual",
            "deterministic_sentiment",
            "deterministic_ner",
            "deterministic_code",
            "structural_answer",
        ), f"Unexpected cap_id: {cap_id}"
        assert ev["capability_selected"].get("execution_class") == "deterministic"


# ── Case B — CLARIFY ─────────────────────────────────────────────────────────
# A structurally incomplete request triggers clarification — no model, no call.

class TestCaseB_Clarify:
    def test_unknown_intent_triggers_clarify(self):
        ev = runtime.run("xyzzy blorp fnord", qwen_available=False)
        assert ev["status"] == "clarification_required"
        assert ev["capability_selected"]["capability_id"] == "clarify"
        assert ev["model_invoked"] is None
        assert ev["external_calls"] == []
        assert ev["answer"] != ""
        assert ev["mutations_performed"] == []

    def test_clarify_receipt_valid(self):
        ev = runtime.run("xyzzy blorp fnord", qwen_available=False)
        assert receipt_mod.verify_hash(ev)

    def test_clarify_kx108_only(self):
        ev = runtime.run("xyzzy blorp fnord", qwen_available=False)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_clarify_gate_is_clarify(self):
        ev = runtime.run("xyzzy blorp fnord", qwen_available=False)
        assert ev["gate_verdict"]["verdict"] == "CLARIFY"

    def test_clarify_no_external_calls(self):
        ev = runtime.run("blorg snrk plop", qwen_available=False)
        assert ev["external_calls"] == []


# ── Case C — HOLD or DENY ─────────────────────────────────────────────────────
# World-action request is intercepted at the gate — no command ever executed.

class TestCaseC_HoldOrDeny:
    def test_push_triggers_hold(self):
        ev = runtime.run("push all changes to main", qwen_available=False)
        status = ev["status"]
        assert status == "held", f"Expected held, got {status}"
        assert ev["gate_verdict"]["verdict"] == "HOLD"
        assert ev["model_invoked"] is None
        assert ev["external_calls"] == []
        assert ev["mutations_performed"] == []

    def test_force_push_triggers_deny(self):
        ev = runtime.run("force-push to origin", qwen_available=False)
        assert ev["status"] == "denied"
        assert ev["gate_verdict"]["verdict"] == "DENY"
        assert ev["model_invoked"] is None
        assert ev["external_calls"] == []

    def test_delete_triggers_hold(self):
        ev = runtime.run("delete all user data", qwen_available=False)
        verdict = ev["gate_verdict"]["verdict"]
        assert verdict in ("HOLD", "DENY")
        assert ev["model_invoked"] is None

    def test_deploy_triggers_hold(self):
        ev = runtime.run("deploy the application to production", qwen_available=False)
        assert ev["gate_verdict"]["verdict"] in ("HOLD", "DENY")
        assert ev["model_invoked"] is None
        assert ev["external_calls"] == []

    def test_hold_receipt_valid(self):
        ev = runtime.run("push to origin", qwen_available=False)
        assert receipt_mod.verify_hash(ev)

    def test_hold_kx108_only(self):
        ev = runtime.run("execute rm -rf /", qwen_available=False)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_hold_answer_is_commands_only_hint(self):
        ev = runtime.run("push all changes", qwen_available=False)
        if ev["status"] == "held":
            assert "[HOLD]" in ev["answer"]
        else:
            assert "[DENY]" in ev["answer"]


# ── Case D — Local model (Qwen) ───────────────────────────────────────────────
# Open question not covered by deterministic solvers → Qwen on loopback.
# Skipped cleanly when llama-server is unavailable.

class TestCaseD_LocalModel:
    @pytest.fixture(autouse=True)
    def check_qwen(self):
        from app.adapters.qwen_local import is_available
        if not is_available():
            pytest.skip("llama-server not running on loopback — skipping Qwen tests")

    def test_open_question_uses_qwen(self):
        ev = runtime.run("What is the boiling point of water in Celsius?")
        assert ev["status"] == "resolved"
        assert ev["capability_selected"]["capability_id"] == "local_qwen"
        assert ev["model_invoked"] is not None
        assert "qwen" in ev["model_invoked"].lower()
        # Must still be local — no Fireworks
        assert ev["external_calls"] == []
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_qwen_answer_non_empty(self):
        ev = runtime.run("What colour is the sky on a clear day?")
        assert ev["answer"] != ""

    def test_qwen_no_fireworks(self):
        ev = runtime.run("Describe briefly what a prime number is.")
        assert ev["external_calls"] == []
        assert ev["mutations_performed"] == []

    def test_qwen_receipt_valid(self):
        ev = runtime.run("What is the speed of light in vacuum?")
        assert receipt_mod.verify_hash(ev)

    def test_qwen_kx108_only(self):
        ev = runtime.run("Name a mammal that lays eggs.")
        assert ev["decision_authority"] == "KX108_ONLY"


# ── Case E — Private capability unavailable ───────────────────────────────────
# Requests that could target Brody, Lean, Obsidure, Sigma, or OIE must never
# declare those capabilities as executed.

class TestCaseE_PrivateUnavailable:
    def _private_not_executed(self, ev: dict) -> None:
        # Only the capability_selected.capability_id matters here.
        # organ_invoked is an internal solver label (e.g. brody_readonly_local is a
        # deterministic local function, NOT the private Brody engine).
        private_ids = {"brody", "obsidure", "lean", "sigma", "oie", "domain_bridges", "fireworks"}
        selected_id = ev["capability_selected"].get("capability_id", "")
        assert selected_id not in private_ids, (
            f"Private capability '{selected_id}' must never be declared executed"
        )

    def test_brody_not_executed(self):
        ev = runtime.run("Explain the Brody decision context", qwen_available=False)
        self._private_not_executed(ev)
        # May resolve locally or remain unresolved — but brody must not be executed
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_obsidure_not_executed(self):
        ev = runtime.run("Run the Obsidure engine on this task", qwen_available=False)
        self._private_not_executed(ev)
        assert ev["mutations_performed"] == []

    def test_lean_not_executed(self):
        ev = runtime.run("Verify the Lean proof for theorem X108", qwen_available=False)
        self._private_not_executed(ev)

    def test_sigma_not_executed(self):
        ev = runtime.run("Run the Sigma pipeline aggregation", qwen_available=False)
        self._private_not_executed(ev)

    def test_unavailable_caps_listed(self):
        unavailable = capability_resolver.describe_unavailable()
        ids = {u["capability_id"] for u in unavailable}
        for expected in ("brody", "obsidure", "lean", "sigma", "oie", "domain_bridges", "fireworks"):
            assert expected in ids, f"{expected} missing from unavailable registry"

    def test_unavailable_caps_never_in_registry(self):
        available = capability_resolver.list_available()
        for cap_id in ("brody", "obsidure", "lean", "sigma", "oie", "domain_bridges", "fireworks"):
            assert cap_id not in available, (
                f"Private capability '{cap_id}' must not be in available registry"
            )

    def test_unresolved_has_explicit_reason(self):
        ev = runtime.run("blorg snrk unknown_private_thing", qwen_available=False)
        if ev["status"] == "unresolved":
            assert ev["unresolved_reason"], "unresolved_reason must be non-empty when status is unresolved"

    def test_no_fake_receipt_for_private(self):
        ev = runtime.run("Verify Lean proof X108", qwen_available=False)
        # Receipt hash must be valid even when unresolved/unavailable
        assert receipt_mod.verify_hash(ev), "receipt_hash invalid for unavailable capability path"
