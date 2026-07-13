"""T3-C1 — full escalation ladder tests: LEVEL 0-3, Brody readonly, memory, replay.

Scenarios:
  A  LEVEL_0 HOLD — "Deploy …" → held, no model, no memory
  B  LEVEL_0 CLARIFY — garbled input → clarification_required
  C  LEVEL_1 — word-multiply math → 432 via T3 solver
  D  LEVEL_2 memory HIT — Obsidia routing query → memory_hit=True
  E  LEVEL_2 memory MISS + UNRESOLVED — chemistry query, no Brody/Qwen
  F  LEVEL_3 Brody readonly mock — called once, Qwen skipped
  G  LEVEL_3 Qwen mock (Brody unavail) — Qwen called once
  H  Brody stub never resolved — invariant check
  I  Route-only V3B entries never executed — static invariant
  J  Replay for C, D, F, G — HASH_VALID YES, REPLAY_MATCH YES, model_called=False
"""
from __future__ import annotations

import contextlib
import http.server
import json
import os
import socket
import threading

import pytest

from app.track3 import capability_resolver
from app.track3 import receipt as receipt_mod
from app.track3 import replay as replay_mod
from app.track3 import runtime
from app.track3 import v3b_surface

# Private capabilities that must never appear as resolved answers
_PRIVATE_CAPS = frozenset(
    {"brody", "obsidure", "lean", "sigma", "oie",
     "domain_bridges", "fireworks", "brody_stub"}
)

# Open query: no deterministic solver match, no memory match.
# Used for LEVEL_3 scenarios (Brody, Qwen).
_OPEN_QUERY = "How does the observer effect influence measurement in quantum mechanics?"


# ── Mock Qwen server (same pattern as lot_b) ─────────────────────────────────

class _MockQwenHandler(http.server.BaseHTTPRequestHandler):
    _response: str = "Mock Qwen answer."
    _call_count: int = 0

    def do_GET(self):
        if self.path in ("/health", "/v1/health"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        _MockQwenHandler._call_count += 1
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = json.dumps({
            "choices": [{"message": {"content": _MockQwenHandler._response}}],
            "usage":   {"completion_tokens": 8, "total_tokens": 40},
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


@contextlib.contextmanager
def _mock_qwen(response: str = "Mock Qwen answer."):
    _MockQwenHandler._response = response
    _MockQwenHandler._call_count = 0
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = http.server.HTTPServer(("127.0.0.1", port), _MockQwenHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    endpoint = f"http://127.0.0.1:{port}/v1"
    try:
        yield endpoint, server
    finally:
        server.shutdown()
        t.join(timeout=2)


# ── Mock Brody server ─────────────────────────────────────────────────────────

class _MockBrodyHandler(http.server.BaseHTTPRequestHandler):
    _response: str = "Mock Brody readonly answer."
    _post_count: int = 0

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        _MockBrodyHandler._post_count += 1
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = json.dumps({
            "response":           _MockBrodyHandler._response,
            "decision_authority": "KX108_ONLY",
            "emits_act":          False,
            "memory_write":       False,
            "kernel_mutation":    False,
            "advisory_only":      True,
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


@contextlib.contextmanager
def _mock_brody(response: str = "Mock Brody readonly answer."):
    _MockBrodyHandler._response = response
    _MockBrodyHandler._post_count = 0
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = http.server.HTTPServer(("127.0.0.1", port), _MockBrodyHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield port, server
    finally:
        server.shutdown()
        t.join(timeout=2)


# ── Scenario A — LEVEL_0 HOLD ─────────────────────────────────────────────────

class TestScenarioA_Level0Hold:
    _INPUT = "Deploy the current branch to production immediately."

    def test_gate_hold_or_deny(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["gate_verdict"]["verdict"] in ("HOLD", "DENY")

    def test_status_held_or_denied(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["status"] in ("held", "denied")

    def test_escalation_level_0(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["escalation_level_final"] == "LEVEL_0"

    def test_no_model(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["model_invoked"] is None

    def test_memory_not_attempted(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["memory_attempted"] is False

    def test_brody_not_attempted(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["brody_readonly_attempted"] is False

    def test_qwen_not_attempted(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["qwen_attempted"] is False

    def test_trace_level0_only(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        levels = {e["level"] for e in ev.get("escalation_trace", [])}
        assert "LEVEL_0" in levels
        assert "LEVEL_1" not in levels
        assert "LEVEL_2" not in levels
        assert "LEVEL_3" not in levels

    def test_kx108_only(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_no_mutations(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["mutations_performed"] == []

    def test_fireworks_false(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["fireworks_attempted"] is False

    def test_tokens_remote_zero(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["tokens_remote"] == 0

    def test_receipt_valid(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert receipt_mod.verify_hash(ev)

    def test_schema_version_2(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["schema_version"] == "track3/2.0"


# ── Scenario B — LEVEL_0 CLARIFY ─────────────────────────────────────────────

class TestScenarioB_Level0Clarify:
    _INPUT = "blorp fnord zrxq"

    def test_status_clarification_required(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["status"] == "clarification_required"

    def test_gate_clarify(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["gate_verdict"]["verdict"] == "CLARIFY"

    def test_escalation_level_0(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["escalation_level_final"] == "LEVEL_0"

    def test_no_model(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["model_invoked"] is None

    def test_memory_not_attempted(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["memory_attempted"] is False

    def test_kx108_only(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_receipt_valid(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert receipt_mod.verify_hash(ev)

    def test_answer_not_empty(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["answer"].strip() != ""


# ── Scenario C — LEVEL_1 deterministic solver (word-multiply) ────────────────

class TestScenarioC_Level1Solver:
    _INPUT = "A warehouse contains 24 boxes with 18 items in each box. How many items are there in total?"

    def test_answer_432(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["status"] == "resolved"
        assert ev["answer"] == "432"

    def test_escalation_level_1(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["escalation_level_final"] == "LEVEL_1"

    def test_local_solver_attempted(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["local_solver_attempted"] is True

    def test_memory_not_attempted(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["memory_attempted"] is False

    def test_no_model(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["model_invoked"] is None

    def test_model_avoided(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["model_avoided"] is True

    def test_cap_deterministic(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["capability_selected"]["capability_id"] == "deterministic_math"

    def test_trace_has_level1(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        levels = {e["level"] for e in ev.get("escalation_trace", [])}
        assert "LEVEL_1" in levels

    def test_kx108_only(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_receipt_valid(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert receipt_mod.verify_hash(ev)


# ── Scenario D — LEVEL_2 memory HIT ─────────────────────────────────────────

class TestScenarioD_Level2MemoryHit:
    _INPUT = "Describe the current state of the Obsidia routing layer."

    def test_memory_hit(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["memory_hit"] is True

    def test_memory_attempted(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["memory_attempted"] is True

    def test_memory_source_current_state(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["memory_source"] == "CURRENT_STATE"

    def test_escalation_level_2(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["escalation_level_final"] == "LEVEL_2"

    def test_status_resolved(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["status"] == "resolved"

    def test_cap_memory_lookup(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["capability_selected"]["capability_id"] == "memory_lookup"

    def test_no_model(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["model_invoked"] is None

    def test_model_avoided(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["model_avoided"] is True

    def test_brody_not_attempted(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["brody_readonly_attempted"] is False

    def test_qwen_not_attempted(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["qwen_attempted"] is False

    def test_trace_has_level2(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        levels = {e["level"] for e in ev.get("escalation_trace", [])}
        assert "LEVEL_2" in levels
        assert "LEVEL_3" not in levels

    def test_kx108_only(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_receipt_valid(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert receipt_mod.verify_hash(ev)

    def test_answer_non_empty(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["answer"].strip() != ""


# ── Scenario E — LEVEL_2 memory MISS → UNRESOLVED ───────────────────────────

class TestScenarioE_Level2MemoryMiss:
    _INPUT = "What is the boiling point of liquid nitrogen?"

    def test_memory_attempted(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["memory_attempted"] is True

    def test_memory_hit_false(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["memory_hit"] is False

    def test_status_unresolved(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["status"] == "unresolved"

    def test_escalation_level_unresolved(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["escalation_level_final"] == "UNRESOLVED"

    def test_brody_not_attempted(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["brody_readonly_attempted"] is False

    def test_qwen_not_attempted(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["qwen_attempted"] is False

    def test_fireworks_false(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["fireworks_attempted"] is False

    def test_kx108_only(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_receipt_valid(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        assert receipt_mod.verify_hash(ev)

    def test_trace_has_all_levels_attempted(self):
        ev = runtime.run(self._INPUT, qwen_available=False, brody_available=False)
        levels = {e["level"] for e in ev.get("escalation_trace", [])}
        assert "LEVEL_0" in levels
        assert "LEVEL_1" in levels
        assert "LEVEL_2" in levels
        assert "LEVEL_3" in levels


# ── Scenario F — LEVEL_3 Brody readonly mock ─────────────────────────────────

class TestScenarioF_Level3BrodyMock:
    _BRODY_ANSWER = "Observer effect: wavefunction collapses upon measurement."

    def _run_with_brody(self, monkeypatch):
        with _mock_brody(self._BRODY_ANSWER) as (port, _):
            monkeypatch.setenv(
                "BRODY_ENDPOINT",
                f"http://127.0.0.1:{port}/api/brody/chat",
            )
            return runtime.run(_OPEN_QUERY, brody_available=None, qwen_available=False)

    def test_status_resolved(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["status"] == "resolved"

    def test_answer_contains_brody_text(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["answer"].strip() != ""
        assert "observer" in ev["answer"].lower() or "wavefunction" in ev["answer"].lower()

    def test_escalation_level_3(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["escalation_level_final"] == "LEVEL_3"

    def test_brody_attempted(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["brody_readonly_attempted"] is True

    def test_brody_available(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["brody_readonly_available"] is True

    def test_qwen_not_attempted(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["qwen_attempted"] is False

    def test_memory_attempted(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["memory_attempted"] is True

    def test_memory_hit_false(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["memory_hit"] is False

    def test_cap_brody_readonly(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["capability_selected"]["capability_id"] == "brody_readonly"

    def test_cap_not_private(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["capability_selected"]["capability_id"] not in _PRIVATE_CAPS

    def test_brody_called_once(self, monkeypatch):
        with _mock_brody(self._BRODY_ANSWER) as (port, _):
            monkeypatch.setenv(
                "BRODY_ENDPOINT",
                f"http://127.0.0.1:{port}/api/brody/chat",
            )
            _MockBrodyHandler._post_count = 0
            runtime.run(_OPEN_QUERY, brody_available=None, qwen_available=False)
        assert _MockBrodyHandler._post_count == 1, (
            f"Expected exactly 1 Brody POST call, got {_MockBrodyHandler._post_count}"
        )

    def test_no_mutations(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["mutations_performed"] == []

    def test_fireworks_false(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["fireworks_attempted"] is False

    def test_tokens_remote_zero(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["tokens_remote"] == 0

    def test_kx108_only(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_receipt_valid(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        assert receipt_mod.verify_hash(ev)

    def test_trace_has_level3_brody(self, monkeypatch):
        ev = self._run_with_brody(monkeypatch)
        l3_events = [
            e for e in ev.get("escalation_trace", [])
            if e["level"] == "LEVEL_3" and e["component"] == "brody_readonly_adapter"
        ]
        assert l3_events, "Expected LEVEL_3 brody event in escalation_trace"
        assert l3_events[0]["selected"] is True


# ── Scenario G — LEVEL_3 Qwen mock (Brody unavailable) ───────────────────────

class TestScenarioG_Level3QwenMock:
    _QWEN_ANSWER = "The observer effect describes how measurement changes the state of a particle."

    def _run_with_qwen(self, monkeypatch):
        with _mock_qwen(self._QWEN_ANSWER) as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            return runtime.run(_OPEN_QUERY, qwen_available=True, brody_available=False)

    def test_status_resolved(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        assert ev["status"] == "resolved"

    def test_answer_non_empty(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        assert ev["answer"].strip() != ""

    def test_escalation_level_3(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        assert ev["escalation_level_final"] == "LEVEL_3"

    def test_qwen_attempted(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        assert ev["qwen_attempted"] is True

    def test_brody_not_attempted(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        assert ev["brody_readonly_attempted"] is False

    def test_memory_attempted(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        assert ev["memory_attempted"] is True

    def test_cap_local_qwen(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        assert ev["capability_selected"]["capability_id"] == "local_qwen"

    def test_cap_not_private(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        assert ev["capability_selected"]["capability_id"] not in _PRIVATE_CAPS

    def test_qwen_called_once(self, monkeypatch):
        with _mock_qwen(self._QWEN_ANSWER) as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            _MockQwenHandler._call_count = 0
            runtime.run(_OPEN_QUERY, qwen_available=True, brody_available=False)
        assert _MockQwenHandler._call_count <= 1, (
            f"Expected at most 1 Qwen call, got {_MockQwenHandler._call_count}"
        )

    def test_no_mutations(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        assert ev["mutations_performed"] == []

    def test_fireworks_false(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        assert ev["fireworks_attempted"] is False

    def test_tokens_remote_zero(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        assert ev["tokens_remote"] == 0

    def test_kx108_only(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_receipt_valid(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        assert receipt_mod.verify_hash(ev)

    def test_trace_has_brody_unavail_then_qwen_selected(self, monkeypatch):
        ev = self._run_with_qwen(monkeypatch)
        brody_ev = [
            e for e in ev.get("escalation_trace", [])
            if e.get("component") == "brody_readonly_adapter"
        ]
        qwen_ev = [
            e for e in ev.get("escalation_trace", [])
            if e.get("component") == "qwen_local_adapter"
        ]
        assert brody_ev, "Expected brody trace event"
        assert brody_ev[0]["available"] is False
        assert qwen_ev, "Expected qwen trace event"
        assert qwen_ev[0]["selected"] is True


# ── Scenario H — Brody stub never resolved ───────────────────────────────────

class TestScenarioH_BrodyStubNeverResolved:
    """brody_stub is a route_marker_only — must never be accepted as a resolved answer."""

    def test_stub_in_unavailable_registry(self):
        unavail = capability_resolver.UNAVAILABLE_CAPABILITIES
        assert "brody" in unavail
        assert "stub" in unavail["brody"].lower() or "private" in unavail["brody"].lower()

    def test_stub_not_in_available_registry(self):
        avail = capability_resolver.list_available()
        assert "brody_stub" not in avail

    def test_brody_stub_never_selected_on_allow(self):
        ev = runtime.run(
            "What is the capital of France?",
            qwen_available=False, brody_available=False,
        )
        assert ev["capability_selected"]["capability_id"] != "brody_stub"

    def test_brody_stub_never_selected_on_open(self):
        ev = runtime.run(_OPEN_QUERY, qwen_available=False, brody_available=False)
        cap = ev["capability_selected"]["capability_id"]
        assert cap not in _PRIVATE_CAPS, (
            f"Private capability appeared as resolved answer: {cap!r}"
        )

    def test_resolved_status_never_from_stub(self):
        for raw in [
            "What is 12 * 12?",
            "Describe the Brody routing engine.",
            _OPEN_QUERY,
        ]:
            ev = runtime.run(raw, qwen_available=False, brody_available=False)
            if ev["status"] == "resolved":
                assert ev["capability_selected"]["capability_id"] not in _PRIVATE_CAPS


# ── Scenario I — Route-only V3B entries never executed ───────────────────────

class TestScenarioI_RouteOnlyNeverExecuted:
    """V3B private route families surface as route_only — no execution in T3."""

    def test_route_only_entries_exist(self):
        route_only = v3b_surface.get_unavailable_v3b_routes()
        bridge_types = {r["bridge_type"] for r in route_only}
        expected = {
            "OBSIDURE_PROPOSAL_READONLY",
            "LEAN_PROOF_CHECK",
            "DOMAIN_BANK",
            "DOMAIN_TRADING",
            "DOMAIN_GPS",
        }
        assert expected.issubset(bridge_types), (
            f"Missing route_only bridges: {expected - bridge_types}"
        )

    def test_route_only_executed_false(self):
        for r in v3b_surface.get_unavailable_v3b_routes():
            assert r["executed"] is False, (
                f"Route-only bridge {r['bridge_type']} has executed=True — invariant violated"
            )

    def test_route_only_decision_authority_kx108(self):
        for r in v3b_surface.get_v3b_route_statuses():
            assert r["decision_authority"] == "KX108_ONLY"

    def test_obsidure_never_selected(self):
        ev = runtime.run(
            "Verify the Lean 4 proof for theorem T108",
            qwen_available=False, brody_available=False,
        )
        cap = ev["capability_selected"]["capability_id"]
        assert cap not in {"obsidure", "lean", "sigma"}

    def test_private_caps_in_unavailable(self):
        unavail_ids = {d["capability_id"] for d in capability_resolver.describe_unavailable()}
        for cap in ("brody", "obsidure", "lean", "sigma", "oie", "fireworks"):
            assert cap in unavail_ids, f"{cap!r} not listed in unavailable capabilities"

    def test_no_private_cap_ever_selected(self):
        for raw in [
            "Verify the Lean 4 proof for theorem T108",
            "Run obsidure analysis on the gateway module",
            "Check sigma aggregation for route T-17",
        ]:
            ev = runtime.run(raw, qwen_available=False, brody_available=False)
            assert ev["capability_selected"]["capability_id"] not in _PRIVATE_CAPS


# ── Scenario J — Replay for C, D, F, G ───────────────────────────────────────

class TestScenarioJ_ReplayEscalation:

    def _save(self, tmp_path, ev: dict, name: str) -> str:
        import json
        f = tmp_path / f"{name}.json"
        f.write_text(json.dumps(ev, default=str), encoding="utf-8")
        return str(f)

    def test_replay_c_level1_solver(self, tmp_path):
        raw = "A warehouse contains 24 boxes with 18 items in each box. How many items are there in total?"
        ev = runtime.run(raw, qwen_available=False, brody_available=False)
        assert ev["status"] == "resolved"
        path = self._save(tmp_path, ev, "c_level1")
        report = replay_mod.replay(path)
        assert report["HASH_VALID"]   == "YES", f"Hash invalid: {report}"
        assert report["REPLAY_MATCH"] == "YES", f"Replay mismatch: {report}"
        assert report["model_called"] is False
        assert report["external_calls"] == 0
        assert report["level_match"] is True

    def test_replay_d_level2_memory(self, tmp_path):
        raw = "Describe the current state of the Obsidia routing layer."
        ev = runtime.run(raw, qwen_available=False, brody_available=False)
        assert ev["memory_hit"] is True
        path = self._save(tmp_path, ev, "d_level2")
        report = replay_mod.replay(path)
        assert report["HASH_VALID"]   == "YES", f"Hash invalid: {report}"
        assert report["REPLAY_MATCH"] == "YES", f"Replay mismatch: {report}"
        assert report["model_called"] is False
        assert report["replayed_escalation_level"] == "LEVEL_2"
        assert report["level_match"] is True

    def test_replay_f_level3_brody(self, tmp_path, monkeypatch):
        answer = "Observer effect: wavefunction collapses upon measurement."
        with _mock_brody(answer) as (port, _):
            monkeypatch.setenv(
                "BRODY_ENDPOINT",
                f"http://127.0.0.1:{port}/api/brody/chat",
            )
            ev = runtime.run(_OPEN_QUERY, brody_available=None, qwen_available=False)
        assert ev["status"] == "resolved"
        assert ev["escalation_level_final"] == "LEVEL_3"
        path = self._save(tmp_path, ev, "f_brody")
        report = replay_mod.replay(path)
        assert report["HASH_VALID"]   == "YES", f"Hash invalid: {report}"
        assert report["REPLAY_MATCH"] == "YES", f"Replay mismatch: {report}"
        assert report["model_called"] is False
        assert report["level_match"]  is True  # lenient for LEVEL_3

    def test_replay_g_level3_qwen(self, tmp_path, monkeypatch):
        answer = "The observer effect describes how measurement changes particle state."
        with _mock_qwen(answer) as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            ev = runtime.run(_OPEN_QUERY, qwen_available=True, brody_available=False)
        assert ev["status"] == "resolved"
        assert ev["escalation_level_final"] == "LEVEL_3"
        path = self._save(tmp_path, ev, "g_qwen")
        report = replay_mod.replay(path)
        assert report["HASH_VALID"]   == "YES", f"Hash invalid: {report}"
        assert report["REPLAY_MATCH"] == "YES", f"Replay mismatch: {report}"
        assert report["model_called"] is False
        assert report["level_match"]  is True

    def test_tamper_detected(self, tmp_path):
        import json
        raw = "A warehouse contains 24 boxes with 18 items in each box. How many items are there in total?"
        ev = runtime.run(raw, qwen_available=False, brody_available=False)
        ev_tampered = dict(ev)
        ev_tampered["answer"] = "999"
        path = self._save(tmp_path, ev_tampered, "tampered")
        report = replay_mod.replay(path)
        assert report["HASH_VALID"]   == "NO"
        assert report["REPLAY_MATCH"] == "NO"


# ── Global invariants across scenarios ───────────────────────────────────────

class TestGlobalInvariants:
    _REQUESTS = [
        ("gate",    "Deploy the current branch to production.",  {"brody_available": False}),
        ("clarify", "blorp fnord zrxq",                         {"brody_available": False}),
        ("math",    "What is 6 times 7?",                       {"brody_available": False}),
        ("memory",  "Describe the current state of the Obsidia routing layer.",
                                                                 {"brody_available": False}),
        ("open",    _OPEN_QUERY,                                 {"qwen_available": False,
                                                                  "brody_available": False}),
    ]

    def test_fireworks_never_attempted(self):
        for _, raw, kw in self._REQUESTS:
            ev = runtime.run(raw, **kw)
            assert ev["fireworks_attempted"] is False, (
                f"fireworks_attempted=True for {raw!r}"
            )

    def test_tokens_remote_always_zero(self):
        for _, raw, kw in self._REQUESTS:
            ev = runtime.run(raw, **kw)
            assert ev["tokens_remote"] == 0, (
                f"tokens_remote != 0 for {raw!r}"
            )

    def test_mutations_always_empty(self):
        for _, raw, kw in self._REQUESTS:
            ev = runtime.run(raw, **kw)
            assert ev["mutations_performed"] == [], (
                f"mutations non-empty for {raw!r}"
            )

    def test_kx108_always(self):
        for _, raw, kw in self._REQUESTS:
            ev = runtime.run(raw, **kw)
            assert ev["decision_authority"] == "KX108_ONLY", (
                f"decision_authority != KX108_ONLY for {raw!r}"
            )

    def test_schema_version_2_always(self):
        for _, raw, kw in self._REQUESTS:
            ev = runtime.run(raw, **kw)
            assert ev["schema_version"] == "track3/2.0"

    def test_receipt_always_valid(self):
        for _, raw, kw in self._REQUESTS:
            ev = runtime.run(raw, **kw)
            assert receipt_mod.verify_hash(ev), (
                f"Invalid receipt for {raw!r}"
            )

    def test_private_cap_never_selected(self):
        for _, raw, kw in self._REQUESTS:
            ev = runtime.run(raw, **kw)
            cap = ev["capability_selected"]["capability_id"]
            assert cap not in _PRIVATE_CAPS, (
                f"Private cap {cap!r} selected for {raw!r}"
            )

    def test_escalation_trace_non_empty(self):
        for _, raw, kw in self._REQUESTS:
            ev = runtime.run(raw, **kw)
            trace = ev.get("escalation_trace", [])
            assert len(trace) >= 1, f"Empty trace for {raw!r}"

    def test_escalation_trace_sequences_ordered(self):
        for _, raw, kw in self._REQUESTS:
            ev = runtime.run(raw, **kw)
            seqs = [e["sequence"] for e in ev.get("escalation_trace", [])]
            assert seqs == sorted(seqs), (
                f"Trace sequences out of order for {raw!r}: {seqs}"
            )

    def test_level0_always_first(self):
        for _, raw, kw in self._REQUESTS:
            ev = runtime.run(raw, **kw)
            trace = ev.get("escalation_trace", [])
            if trace:
                assert trace[0]["level"] == "LEVEL_0", (
                    f"First trace event not LEVEL_0 for {raw!r}: {trace[0]['level']}"
                )
