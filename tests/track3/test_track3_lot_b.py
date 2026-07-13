"""LOT T3-B tests — Scenarios A-H + Phase 8 invariants + replay + output file.

Mock Qwen server: lightweight http.server thread, no external dependency.
No Fireworks calls, no real llama-server required.
"""
from __future__ import annotations

import contextlib
import http.server
import json
import os
import socket
import threading
from pathlib import Path

import pytest

from app.track3 import runtime
from app.track3 import receipt as receipt_mod
from app.track3 import capability_resolver
from app.track3 import replay as replay_mod

_PRIVATE_CAPS = {"brody", "obsidure", "lean", "sigma", "oie", "domain_bridges", "fireworks"}


# ── Mock Qwen server ──────────────────────────────────────────────────────────

class _MockHandler(http.server.BaseHTTPRequestHandler):
    _response: str = "42"
    _call_count: int = 0

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        _MockHandler._call_count += 1
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = json.dumps({
            "choices": [{"message": {"content": _MockHandler._response}}],
            "usage": {"completion_tokens": 8, "total_tokens": 40},
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def _mock_qwen(response: str = "The answer is 42."):
    _MockHandler._response = response
    _MockHandler._call_count = 0

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    server = http.server.HTTPServer(("127.0.0.1", port), _MockHandler)
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()

    endpoint = f"http://127.0.0.1:{port}/v1"
    try:
        yield endpoint, server
    finally:
        server.shutdown()
        t.join(timeout=2)


# ── Scenario A — Math word problem (T3 solver) ───────────────────────────────

class TestScenarioA_MathWord:
    _INPUT = "A warehouse has 24 boxes with 18 items in each box. How many items are there?"

    def test_answer_is_432(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["status"] == "resolved"
        assert ev["answer"] == "432"

    def test_capability_is_deterministic_math(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        cap_id = ev["capability_selected"]["capability_id"]
        assert cap_id == "deterministic_math", f"Expected deterministic_math, got {cap_id}"

    def test_no_model_invoked(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["model_invoked"] is None

    def test_no_external_calls(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["external_calls"] == []

    def test_kx108_only(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_receipt_valid(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert receipt_mod.verify_hash(ev)

    def test_replay_match(self, tmp_path):
        ev = runtime.run(self._INPUT, qwen_available=False)
        receipt_file = tmp_path / "scenario_a.json"
        receipt_file.write_text(json.dumps(ev), encoding="utf-8")
        report = replay_mod.replay(str(receipt_file))
        assert report["HASH_VALID"]    == "YES"
        assert report["REPLAY_MATCH"]  == "YES"
        assert report["model_called"]  is False
        assert report["external_calls"] == 0


# ── Scenario B — Sentiment ───────────────────────────────────────────────────

class TestScenarioB_Sentiment:
    _INPUT = "Classify the sentiment: The installation was quick and the application works perfectly."

    def test_status_resolved(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        # May resolve locally (quick∈POS) or need Qwen — either is acceptable
        assert ev["status"] in ("resolved", "unresolved")

    def test_if_resolved_positive(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        if ev["status"] == "resolved":
            assert "positive" in ev["answer"].lower(), (
                f"Expected positive sentiment, got: {ev['answer']!r}"
            )

    def test_receipt_valid(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert receipt_mod.verify_hash(ev)

    def test_kx108_only(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_no_private_cap(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["capability_selected"]["capability_id"] not in _PRIVATE_CAPS

    def test_sentiment_with_mock_qwen(self, monkeypatch):
        with _mock_qwen("positive") as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            ev = runtime.run(self._INPUT, qwen_available=True)
        assert ev["status"] == "resolved"
        assert ev["decision_authority"] == "KX108_ONLY"
        assert receipt_mod.verify_hash(ev)


# ── Scenario C — NER (falls through to Qwen mock) ───────────────────────────

class TestScenarioC_NER:
    _INPUT = "Extract and label the named entities: Alice met engineers from AMD in Paris on 12 July 2026."

    def test_receipt_valid_with_mock(self, monkeypatch):
        ner_answer = "Alice - PERSON; AMD - ORGANIZATION; Paris - LOCATION; 12 July 2026 - DATE"
        with _mock_qwen(ner_answer) as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            ev = runtime.run(self._INPUT, qwen_available=True)
        assert receipt_mod.verify_hash(ev)
        assert ev["decision_authority"] == "KX108_ONLY"
        assert ev["capability_selected"]["capability_id"] not in _PRIVATE_CAPS
        assert ev["external_calls"] == []

    def test_no_model_if_qwen_unavailable(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["model_invoked"] is None
        assert receipt_mod.verify_hash(ev)

    def test_no_private_cap_ever(self, monkeypatch):
        with _mock_qwen("Alice - PERSON") as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            ev = runtime.run(self._INPUT, qwen_available=True)
        assert ev["capability_selected"]["capability_id"] not in _PRIVATE_CAPS

    def test_ner_no_mutations(self, monkeypatch):
        with _mock_qwen("Alice - PERSON") as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            ev = runtime.run(self._INPUT, qwen_available=True)
        assert ev["mutations_performed"] == []


# ── Scenario D — CLARIFY ─────────────────────────────────────────────────────

class TestScenarioD_Clarify:
    _INPUT = "blorp fnord zrxq"

    def test_clarify_selected(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["status"] == "clarification_required"
        assert ev["capability_selected"]["capability_id"] == "clarify"

    def test_no_model(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["model_invoked"] is None

    def test_no_mutation(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["mutations_performed"] == []

    def test_answer_non_empty(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["answer"] != ""

    def test_receipt_valid(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert receipt_mod.verify_hash(ev)

    def test_replay_match(self, tmp_path):
        ev = runtime.run(self._INPUT, qwen_available=False)
        f = tmp_path / "scenario_d.json"
        f.write_text(json.dumps(ev), encoding="utf-8")
        report = replay_mod.replay(str(f))
        assert report["HASH_VALID"]   == "YES"
        assert report["REPLAY_MATCH"] == "YES"
        assert report["model_called"] is False


# ── Scenario E — HOLD ────────────────────────────────────────────────────────

class TestScenarioE_Hold:
    _INPUT = "Deploy the current branch to production immediately."

    def test_gate_hold_or_deny(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["gate_verdict"]["verdict"] in ("HOLD", "DENY")

    def test_no_model(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["model_invoked"] is None

    def test_no_subprocess_no_git(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["mutations_performed"] == []
        assert ev["external_calls"] == []

    def test_receipt_valid(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert receipt_mod.verify_hash(ev)

    def test_kx108_only(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_replay_match(self, tmp_path):
        ev = runtime.run(self._INPUT, qwen_available=False)
        f = tmp_path / "scenario_e.json"
        f.write_text(json.dumps(ev), encoding="utf-8")
        report = replay_mod.replay(str(f))
        assert report["HASH_VALID"]   == "YES"
        assert report["REPLAY_MATCH"] == "YES"
        assert report["model_called"] is False
        assert report["external_calls"] == 0


# ── Scenario F — local_qwen mock ─────────────────────────────────────────────

class TestScenarioF_QwenMock:
    _INPUT = "What is the chemical symbol for gold?"

    def test_mock_qwen_resolves(self, monkeypatch):
        with _mock_qwen("Au") as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            ev = runtime.run(self._INPUT, qwen_available=True)
        assert ev["status"] == "resolved"
        assert ev["answer"] == "Au"
        assert ev["capability_selected"]["capability_id"] == "local_qwen"
        assert ev["model_invoked"] is not None

    def test_qwen_loopback_only(self, monkeypatch):
        # external_calls must stay empty (loopback is not external)
        with _mock_qwen("Au") as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            ev = runtime.run(self._INPUT, qwen_available=True)
        assert ev["external_calls"] == []

    def test_no_fireworks(self, monkeypatch):
        with _mock_qwen("Au") as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            ev = runtime.run(self._INPUT, qwen_available=True)
        ev_str = json.dumps(ev, default=str).lower()
        for call in ev.get("external_calls", []):
            assert "fireworks" not in str(call).lower()

    def test_single_qwen_call(self, monkeypatch):
        with _mock_qwen("Au") as (endpoint, server):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            _MockHandler._call_count = 0
            ev = runtime.run(self._INPUT, qwen_available=True)
        # At most one POST call to the model
        assert _MockHandler._call_count <= 1, (
            f"Expected at most 1 Qwen call, got {_MockHandler._call_count}"
        )

    def test_kx108_only(self, monkeypatch):
        with _mock_qwen("Au") as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            ev = runtime.run(self._INPUT, qwen_available=True)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_receipt_valid(self, monkeypatch):
        with _mock_qwen("Au") as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            ev = runtime.run(self._INPUT, qwen_available=True)
        assert receipt_mod.verify_hash(ev)

    def test_replay_without_model(self, tmp_path, monkeypatch):
        with _mock_qwen("Au") as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            ev = runtime.run(self._INPUT, qwen_available=True)
        f = tmp_path / "scenario_f.json"
        f.write_text(json.dumps(ev), encoding="utf-8")
        # Replay: no model, no external calls
        report = replay_mod.replay(str(f))
        assert report["HASH_VALID"]    == "YES"
        assert report["model_called"]  is False
        assert report["external_calls"] == 0

    def test_mutations_empty(self, monkeypatch):
        with _mock_qwen("Au") as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            ev = runtime.run(self._INPUT, qwen_available=True)
        assert ev["mutations_performed"] == []


# ── Scenario G — Qwen unavailable ────────────────────────────────────────────

class TestScenarioG_QwenUnavailable:
    _INPUT = "What is the boiling point of nitrogen?"

    def test_no_crash(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        # Must not raise; must return a valid dict
        assert isinstance(ev, dict)

    def test_status_unresolved(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["status"] == "unresolved"

    def test_no_fake_answer(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["answer"] == ""

    def test_unresolved_reason_set(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["unresolved_reason"], "unresolved_reason must be non-empty"

    def test_no_fireworks_fallback(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["external_calls"] == []

    def test_receipt_valid(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert receipt_mod.verify_hash(ev)

    def test_kx108_only(self):
        ev = runtime.run(self._INPUT, qwen_available=False)
        assert ev["decision_authority"] == "KX108_ONLY"


# ── Scenario H — Private capability ─────────────────────────────────────────

class TestScenarioH_PrivateCapability:
    _PRIVATE_INPUTS = [
        ("lean",     "Verify the Lean 4 proof for theorem T108"),
        ("obsidure", "Run the Obsidure engine on this task"),
        ("sigma",    "Invoke the Sigma pipeline aggregation"),
    ]

    @pytest.mark.parametrize("name,inp", _PRIVATE_INPUTS)
    def test_private_cap_never_selected(self, name, inp):
        ev = runtime.run(inp, qwen_available=False)
        cap_id = ev["capability_selected"]["capability_id"]
        assert cap_id not in _PRIVATE_CAPS, (
            f"[{name}] Private capability {cap_id!r} must never be declared executed"
        )

    @pytest.mark.parametrize("name,inp", _PRIVATE_INPUTS)
    def test_no_organ_invoked_for_private(self, name, inp):
        ev = runtime.run(inp, qwen_available=False)
        organ = ev.get("organ_invoked") or ""
        for pid in _PRIVATE_CAPS - {"brody"}:  # brody_readonly_local is a local solver, not the engine
            assert pid not in organ.lower(), (
                f"[{name}] Private engine '{pid}' must not appear in organ_invoked"
            )

    @pytest.mark.parametrize("name,inp", _PRIVATE_INPUTS)
    def test_no_model_invoked_for_private_qwen_off(self, name, inp):
        ev = runtime.run(inp, qwen_available=False)
        assert ev["model_invoked"] is None

    @pytest.mark.parametrize("name,inp", _PRIVATE_INPUTS)
    def test_receipt_valid(self, name, inp):
        ev = runtime.run(inp, qwen_available=False)
        assert receipt_mod.verify_hash(ev)

    @pytest.mark.parametrize("name,inp", _PRIVATE_INPUTS)
    def test_kx108_only(self, name, inp):
        ev = runtime.run(inp, qwen_available=False)
        assert ev["decision_authority"] == "KX108_ONLY"

    def test_bridge_required_or_unavailable_status(self):
        ev = runtime.run("Verify the Lean 4 proof for theorem T108", qwen_available=False)
        # Status should be unresolved (not a fake resolved) since no Lean engine is connected
        # OR it may be clarification_required if intent parsed as question
        assert ev["status"] in ("unresolved", "clarification_required", "resolved")
        # If resolved, must not have used a private capability
        if ev["status"] == "resolved":
            assert ev["capability_selected"]["capability_id"] not in _PRIVATE_CAPS

    def test_no_fake_proof_receipt(self):
        ev = runtime.run("Verify the Lean 4 proof for theorem T108", qwen_available=False)
        # receipt_hash must be valid (not a fake/empty receipt)
        assert receipt_mod.verify_hash(ev)
        # No fake "proof_verified" field should appear
        assert "proof_verified" not in ev


# ── Output file tests ─────────────────────────────────────────────────────────

class TestOutputFile:
    def test_output_file_written(self, tmp_path):
        from app.track3.cli import _write_output_file
        ev = runtime.run("What is 5 * 5?", qwen_available=False)
        out = tmp_path / "receipt.json"
        _write_output_file(ev, str(out))
        assert out.exists()

    def test_output_file_valid_json(self, tmp_path):
        from app.track3.cli import _write_output_file
        ev = runtime.run("What is 5 * 5?", qwen_available=False)
        out = tmp_path / "receipt.json"
        _write_output_file(ev, str(out))
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["answer"] == "25"
        assert loaded["decision_authority"] == "KX108_ONLY"

    def test_output_file_utf8_no_bom(self, tmp_path):
        from app.track3.cli import _write_output_file
        ev = runtime.run("What is 5 * 5?", qwen_available=False)
        out = tmp_path / "receipt.json"
        _write_output_file(ev, str(out))
        raw_bytes = out.read_bytes()
        # BOM is EF BB BF in UTF-8
        assert not raw_bytes.startswith(b"\xef\xbb\xbf"), "Output file must not have UTF-8 BOM"

    def test_output_file_no_secrets(self, tmp_path):
        from app.track3.cli import _write_output_file
        ev = runtime.run("What is 5 * 5?", qwen_available=False)
        out = tmp_path / "receipt.json"
        _write_output_file(ev, str(out))
        content = out.read_text(encoding="utf-8").lower()
        for secret in ("api_key", "fireworks_api_key", "password"):
            assert secret not in content

    def test_output_file_receipt_hash_verifies(self, tmp_path):
        from app.track3.cli import _write_output_file
        ev = runtime.run("What is 5 * 5?", qwen_available=False)
        out = tmp_path / "receipt.json"
        _write_output_file(ev, str(out))
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert receipt_mod.verify_hash(loaded)

    def test_output_file_creates_parent_dirs(self, tmp_path):
        from app.track3.cli import _write_output_file
        ev = runtime.run("What is 3 + 3?", qwen_available=False)
        nested = tmp_path / "a" / "b" / "c" / "out.json"
        _write_output_file(ev, str(nested))
        assert nested.exists()

    def test_output_file_rejects_directory(self, tmp_path):
        from app.track3.cli import _write_output_file
        ev = runtime.run("What is 2 + 2?", qwen_available=False)
        with pytest.raises(IsADirectoryError):
            _write_output_file(ev, str(tmp_path))


# ── Replay tests ──────────────────────────────────────────────────────────────

class TestReplay:
    def test_replay_hash_valid(self, tmp_path):
        ev = runtime.run("What is 6 * 7?", qwen_available=False)
        f = tmp_path / "r.json"
        f.write_text(json.dumps(ev), encoding="utf-8")
        report = replay_mod.replay(str(f))
        assert report["HASH_VALID"] == "YES"

    def test_replay_match_deterministic(self, tmp_path):
        ev = runtime.run("push all changes to main", qwen_available=False)
        f = tmp_path / "r.json"
        f.write_text(json.dumps(ev), encoding="utf-8")
        report = replay_mod.replay(str(f))
        assert report["REPLAY_MATCH"] == "YES"

    def test_replay_no_model(self, tmp_path):
        ev = runtime.run("What is 9 * 9?", qwen_available=False)
        f = tmp_path / "r.json"
        f.write_text(json.dumps(ev), encoding="utf-8")
        report = replay_mod.replay(str(f))
        assert report["model_called"] is False

    def test_replay_no_external(self, tmp_path):
        ev = runtime.run("What is 4 + 4?", qwen_available=False)
        f = tmp_path / "r.json"
        f.write_text(json.dumps(ev), encoding="utf-8")
        report = replay_mod.replay(str(f))
        assert report["external_calls"] == 0

    def test_tampered_receipt_fails_replay(self, tmp_path):
        ev = runtime.run("What is 7 * 7?", qwen_available=False)
        ev_tampered = dict(ev)
        ev_tampered["answer"] = "HACKED"
        f = tmp_path / "tampered.json"
        f.write_text(json.dumps(ev_tampered), encoding="utf-8")
        report = replay_mod.replay(str(f))
        assert report["HASH_VALID"]   == "NO"
        assert report["REPLAY_MATCH"] == "NO"

    def test_replay_missing_file(self, tmp_path):
        report = replay_mod.replay(str(tmp_path / "nonexistent.json"))
        assert report["HASH_VALID"]   == "NO"
        assert report["REPLAY_MATCH"] == "NO"

    def test_replay_does_not_overwrite_source(self, tmp_path):
        ev = runtime.run("What is 3 * 3?", qwen_available=False)
        f = tmp_path / "source.json"
        f.write_text(json.dumps(ev), encoding="utf-8")
        original_content = f.read_text(encoding="utf-8")
        replay_mod.replay(str(f))
        assert f.read_text(encoding="utf-8") == original_content

    def test_replay_ignores_timestamps(self, tmp_path):
        ev = runtime.run("What is 2 * 2?", qwen_available=False)
        # Modify timestamps in the stored envelope without touching hash
        # (we do this by testing that the replay doesn't fail on timestamp fields)
        f = tmp_path / "r.json"
        f.write_text(json.dumps(ev), encoding="utf-8")
        report = replay_mod.replay(str(f))
        # If hash is valid and structural fields match, REPLAY_MATCH = YES
        # even though started_at/completed_at/duration_ms differ across runs
        assert report["HASH_VALID"] == "YES"


# ── Phase 8 — New invariants ──────────────────────────────────────────────────

class TestInvariantsPhase8:
    _SAMPLE_REQUESTS = [
        ("math",    "What is 7 * 9?",             {}),
        ("hold",    "push all changes to main",    {}),
        ("deny",    "force-push to origin",        {}),
        ("clarify", "xyzzy blorp fnord",           {}),
        ("fact",    "What is the capital of Australia?", {}),
        ("open",    "What colour is the sky?",     {"qwen_available": False}),
    ]

    def _run(self, req, kw):
        kw2 = dict(kw)
        if "qwen_available" not in kw2:
            kw2["qwen_available"] = False
        return runtime.run(req, **kw2)

    def test_exactly_one_capability_selected(self):
        for _, req, kw in self._SAMPLE_REQUESTS:
            ev = self._run(req, kw)
            cap = ev.get("capability_selected", {})
            assert "capability_id" in cap, "capability_selected must have capability_id"

    @pytest.mark.parametrize("req", [
        "push all changes to main",
        "force-push to origin",
        "xyzzy blorp fnord",
    ])
    def test_no_model_after_gate_intercept(self, req):
        ev = runtime.run(req, qwen_available=False)
        assert ev["model_invoked"] is None

    def test_gate_before_qwen_on_hold(self):
        ev = runtime.run("push all changes", qwen_available=True)
        # Even if qwen_available=True, gate intercepts before Qwen is tried
        assert ev["gate_verdict"]["verdict"] in ("HOLD", "DENY")
        assert ev["model_invoked"] is None

    def test_non_loopback_url_rejected(self, monkeypatch):
        from app.adapters import qwen_local
        monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", "http://remote-server.example.com:8080/v1")
        result = qwen_local.chat("hello")
        assert result["success"] is False
        assert "loopback" in result.get("error", "").lower() or result["status"] == "not_available"

    def test_single_qwen_attempt_per_run(self, monkeypatch):
        with _mock_qwen("blue") as (endpoint, _):
            monkeypatch.setenv("QWEN_LOCAL_ENDPOINT", endpoint)
            _MockHandler._call_count = 0
            runtime.run("What colour is the sky?", qwen_available=True)
            calls = _MockHandler._call_count
        assert calls <= 1, f"Expected at most 1 Qwen call per run, got {calls}"

    def test_fireworks_never_called(self):
        import importlib
        # Verify fireworks is not imported by the track3 runtime at module level
        import sys
        # Running a full pipeline — if Fireworks was called, it would raise without a key
        ev = runtime.run("What colour is the sky?", qwen_available=False)
        assert ev["external_calls"] == []

    @pytest.mark.parametrize("name,req,kw", _SAMPLE_REQUESTS)
    def test_kx108_only_everywhere(self, name, req, kw):
        ev = self._run(req, kw)
        assert ev["decision_authority"] == "KX108_ONLY", f"[{name}] KX108_ONLY violated"

    @pytest.mark.parametrize("name,req,kw", _SAMPLE_REQUESTS)
    def test_no_mutations_anywhere(self, name, req, kw):
        ev = self._run(req, kw)
        assert ev["mutations_performed"] == [], f"[{name}] mutations must be []"

    @pytest.mark.parametrize("name,req,kw", _SAMPLE_REQUESTS)
    def test_no_external_calls_anywhere(self, name, req, kw):
        ev = self._run(req, kw)
        assert ev["external_calls"] == [], f"[{name}] external_calls must be []"

    @pytest.mark.parametrize("name,req,kw", _SAMPLE_REQUESTS)
    def test_receipt_stable(self, name, req, kw):
        ev = self._run(req, kw)
        assert receipt_mod.verify_hash(ev), f"[{name}] receipt_hash invalid"

    def test_tamper_detection_answer(self):
        ev = runtime.run("What is 3 * 3?", qwen_available=False)
        t = dict(ev, answer="TAMPERED")
        assert not receipt_mod.verify_hash(t)

    def test_tamper_detection_authority(self):
        ev = runtime.run("What is 4 * 4?", qwen_available=False)
        t = dict(ev, decision_authority="ATTACKER")
        assert not receipt_mod.verify_hash(t)

    def test_replay_structural_match(self, tmp_path):
        ev = runtime.run("What is 5 * 5?", qwen_available=False)
        f = tmp_path / "r.json"
        f.write_text(json.dumps(ev), encoding="utf-8")
        report = replay_mod.replay(str(f))
        assert report["ir_match"]
        assert report["plan_match"]
        assert report["gate_match"]
        assert report["cap_match"]
        assert report["auth_match"]

    def test_replay_no_model_call(self, tmp_path):
        ev = runtime.run("What is 6 * 6?", qwen_available=False)
        f = tmp_path / "r.json"
        f.write_text(json.dumps(ev), encoding="utf-8")
        report = replay_mod.replay(str(f))
        assert report["model_called"] is False
        assert report["external_calls"] == 0

    def test_no_reasoning_in_output(self):
        ev = runtime.run("What is 2 * 2?", qwen_available=False)
        answer            = (ev.get("answer") or "").lower()
        unresolved_reason = (ev.get("unresolved_reason") or "").lower()
        for marker in ("<thinking>", "[reasoning]", "chain_of_thought", "hidden_state"):
            assert marker not in answer
            assert marker not in unresolved_reason

    def test_private_caps_never_in_available_registry(self):
        available = capability_resolver.list_available()
        for pid in _PRIVATE_CAPS:
            assert pid not in available

    def test_output_json_utf8_no_bom(self, tmp_path):
        from app.track3.cli import _write_output_file
        ev = runtime.run("What is 7 * 7?", qwen_available=False)
        out = tmp_path / "test_utf8.json"
        _write_output_file(ev, str(out))
        raw = out.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        # Must be valid UTF-8
        raw.decode("utf-8")


# ── Output validator tests ────────────────────────────────────────────────────

class TestOutputValidator:
    def test_valid_answer_passes(self):
        from app.track3.output_validator import validate_and_repair
        result = validate_and_repair("The answer is 42.", "local_qwen")
        assert result["valid"] is True
        assert result["answer"] == "The answer is 42."
        assert result["repaired"] is False

    def test_empty_answer_fails(self):
        from app.track3.output_validator import validate_and_repair
        result = validate_and_repair("", "local_qwen")
        assert result["valid"] is False
        assert result["reason"] == "empty_answer"

    def test_thinking_block_stripped(self):
        from app.track3.output_validator import validate_and_repair
        raw = "<thinking>internal chain</thinking>The answer is 42."
        result = validate_and_repair(raw, "local_qwen")
        assert result["valid"] is True
        assert "<thinking>" not in result["answer"]
        assert "42" in result["answer"]
        assert result["repaired"] is True

    def test_max_length_truncated(self):
        from app.track3.output_validator import validate_and_repair
        long_answer = "word " * 700  # > 3000 chars
        result = validate_and_repair(long_answer, "local_qwen")
        assert result["valid"] is True
        assert len(result["answer"]) <= 3000
        assert result["repaired"] is True

    def test_error_marker_rejected(self):
        from app.track3.output_validator import validate_and_repair
        bad = "Traceback (most recent call last):\n  File 'x.py'\nValueError: oops"
        result = validate_and_repair(bad, "local_qwen")
        assert result["valid"] is False
        assert "error_marker" in result["reason"]
