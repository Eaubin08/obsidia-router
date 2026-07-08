"""Tests — brody_readonly adapter."""
from __future__ import annotations

import json
import os
import threading
import http.server
from unittest.mock import patch

import pytest

from app.adapters import brody_readonly as br


# ── Shape de réponse réelle du vrai Brody (/api/brody/chat) ──────────────────

_REAL_BRODY_RESPONSE = {
    "response": "Brody est actif en mode readonly consultatif.",
    "final_answer": "Brody est actif en mode readonly consultatif.",
    "voice_runtime": "BRODY_V3_FASTPATH",
    "decision_authority": "KX108_ONLY",
    "emits_act": False,
    "advisory_only": True,
    "memory_write": False,
    "graphiti_write": False,
    "kernel_mutation": False,
    "fastpath": True,
}

# Shape minimal (champ "text" classique) — rétrocompatibilité
_LEGACY_TEXT_RESPONSE = {"text": "legacy brody response"}

# Shape avec uniquement "answer"
_ANSWER_ONLY_RESPONSE = {"answer": "answer only"}


def _make_ir(raw: str = "test") -> dict:
    return {
        "raw": raw,
        "intent_type": "question",
        "target_layer": "brody",
        "action_type": "answer",
        "risk_level": "low",
        "needs": {"brody": True, "remote_model": False},
        "constraints": ["router_non_sovereign"],
        "missing": [],
    }


def _make_topic() -> dict:
    return {"topic": "GENERAL", "is_canonical": False}


@pytest.fixture(autouse=True)
def reset():
    br.reset_metrics()
    yield
    br.reset_metrics()


# ── Serveurs mock ─────────────────────────────────────────────────────────────

def _make_server(response_body: dict, status: int = 200):
    """Crée un serveur HTTP qui répond avec le body donné."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            body = json.dumps(response_body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, port


# ── Stub mode (pas de BRODY_ENDPOINT) ────────────────────────────────────────

def test_stub_mode_no_endpoint(monkeypatch):
    monkeypatch.delenv("BRODY_ENDPOINT", raising=False)
    result = br.answer(_make_ir(), _make_topic())
    assert result["brody_mode"] == "stub"
    assert result["remote_tokens"] == 0
    assert result["real_action"] is False
    assert result["memory_write"] is False
    assert result["kernel_mutation"] is False
    assert result["emits_act"] is False
    assert result["decision_authority"] == "KX108_ONLY"


def test_stub_mode_empty_endpoint(monkeypatch):
    monkeypatch.setenv("BRODY_ENDPOINT", "")
    result = br.answer(_make_ir(), _make_topic())
    assert result["brody_mode"] == "stub"


def test_stub_metrics_increment(monkeypatch):
    monkeypatch.delenv("BRODY_ENDPOINT", raising=False)
    br.answer(_make_ir(), _make_topic())
    br.answer(_make_ir(), _make_topic())
    m = br.get_metrics()
    assert m["brody_stub_fallbacks"] == 2
    assert m["brody_live_calls"] == 0
    assert m["brody_errors"] == 0


# ── Fallback mode (endpoint défini mais injoignable) ──────────────────────────

def test_fallback_on_connection_error(monkeypatch):
    monkeypatch.setenv("BRODY_ENDPOINT", "http://127.0.0.1:19999/brody")
    result = br.answer(_make_ir("test fallback"), _make_topic())
    assert result["brody_mode"] == "fallback"
    assert "brody_fallback_reason" in result
    m = br.get_metrics()
    assert m["brody_errors"] == 1
    assert m["brody_stub_fallbacks"] == 1


# ── Live mode — shape réelle du vrai Brody ───────────────────────────────────

def test_live_mode_real_brody_shape(monkeypatch):
    """Le vrai shape Brody (response + final_answer + governance flags) → live."""
    server, port = _make_server(_REAL_BRODY_RESPONSE)
    try:
        monkeypatch.setenv("BRODY_ENDPOINT", f"http://127.0.0.1:{port}/api/brody/chat")
        result = br.answer(_make_ir("test real shape"), _make_topic())
        assert result["brody_mode"] == "live", (
            f"attendu live, obtenu {result['brody_mode']!r} — "
            f"fallback_reason={result.get('brody_fallback_reason')!r}"
        )
        assert result["text"] == "Brody est actif en mode readonly consultatif."
        assert result["real_action"] is False
        assert result["memory_write"] is False
        assert result["kernel_mutation"] is False
        assert result["emits_act"] is False
        assert result["decision_authority"] == "KX108_ONLY"
        m = br.get_metrics()
        assert m["brody_live_calls"] == 1
        assert m["brody_stub_fallbacks"] == 0
        assert m["brody_errors"] == 0
    finally:
        server.shutdown()


def test_live_mode_response_field_priority(monkeypatch):
    """response > final_answer > text > answer."""
    server, port = _make_server(_REAL_BRODY_RESPONSE)
    try:
        monkeypatch.setenv("BRODY_ENDPOINT", f"http://127.0.0.1:{port}/api/brody/chat")
        result = br.answer(_make_ir("priority test"), _make_topic())
        # "response" doit être choisi en premier
        assert result["text"] == _REAL_BRODY_RESPONSE["response"]
    finally:
        server.shutdown()


def test_live_mode_legacy_text_field(monkeypatch):
    """Rétrocompatibilité : champ 'text' accepté si response/final_answer absents."""
    server, port = _make_server(_LEGACY_TEXT_RESPONSE)
    try:
        monkeypatch.setenv("BRODY_ENDPOINT", f"http://127.0.0.1:{port}/api/brody/chat")
        result = br.answer(_make_ir("legacy"), _make_topic())
        assert result["brody_mode"] == "live"
        assert result["text"] == "legacy brody response"
    finally:
        server.shutdown()


def test_live_mode_answer_field(monkeypatch):
    """Champ 'answer' accepté si les autres absents."""
    server, port = _make_server(_ANSWER_ONLY_RESPONSE)
    try:
        monkeypatch.setenv("BRODY_ENDPOINT", f"http://127.0.0.1:{port}/api/brody/chat")
        result = br.answer(_make_ir("answer only"), _make_topic())
        assert result["brody_mode"] == "live"
        assert result["text"] == "answer only"
    finally:
        server.shutdown()


def test_live_mode_fastpath_not_a_failure(monkeypatch):
    """fastpath=true est normal en mode Brody compact readonly — ne doit pas échouer."""
    server, port = _make_server(_REAL_BRODY_RESPONSE)
    try:
        monkeypatch.setenv("BRODY_ENDPOINT", f"http://127.0.0.1:{port}/api/brody/chat")
        result = br.answer(_make_ir("fastpath test"), _make_topic())
        assert result["brody_mode"] == "live"
        m = br.get_metrics()
        assert m["brody_errors"] == 0
    finally:
        server.shutdown()


def test_live_mode_raw_snapshot_present(monkeypatch):
    """Le snapshot 'raw' des champs de gouvernance doit être inclus."""
    server, port = _make_server(_REAL_BRODY_RESPONSE)
    try:
        monkeypatch.setenv("BRODY_ENDPOINT", f"http://127.0.0.1:{port}/api/brody/chat")
        result = br.answer(_make_ir("raw snapshot"), _make_topic())
        assert result["brody_mode"] == "live"
        assert "raw" in result
        raw = result["raw"]
        assert raw.get("decision_authority") == "KX108_ONLY"
        assert raw.get("fastpath") is True
    finally:
        server.shutdown()


def test_live_mode_payload_has_mode_and_compact(monkeypatch):
    """Le payload envoyé doit inclure mode='readonly_stack_test' et compact=True."""
    captured_body: list[bytes] = []

    class _CaptureHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            captured_body.append(self.rfile.read(length))
            body = json.dumps(_REAL_BRODY_RESPONSE).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        monkeypatch.setenv("BRODY_ENDPOINT", f"http://127.0.0.1:{port}/api/brody/chat")
        br.answer(_make_ir("payload check"), _make_topic())
        assert captured_body, "aucun POST reçu"
        payload = json.loads(captured_body[0].decode())
        assert payload.get("mode") == "readonly_stack_test"
        assert payload.get("compact") is True
        assert payload.get("readonly") is True
        assert "message" in payload
    finally:
        server.shutdown()


# ── Gouvernance toujours présente ─────────────────────────────────────────────

@pytest.mark.parametrize("endpoint", [None, "http://127.0.0.1:19999/bad"])
def test_governance_always_present(monkeypatch, endpoint):
    if endpoint:
        monkeypatch.setenv("BRODY_ENDPOINT", endpoint)
    else:
        monkeypatch.delenv("BRODY_ENDPOINT", raising=False)
    result = br.answer(_make_ir(), _make_topic())
    assert result["real_action"] is False
    assert result["memory_write"] is False
    assert result["kernel_mutation"] is False
    assert result["emits_act"] is False
    assert result["decision_authority"] == "KX108_ONLY"


# ── reset_metrics ─────────────────────────────────────────────────────────────

def test_reset_metrics(monkeypatch):
    monkeypatch.delenv("BRODY_ENDPOINT", raising=False)
    br.answer(_make_ir(), _make_topic())
    br.reset_metrics()
    m = br.get_metrics()
    assert m["brody_live_calls"] == 0
    assert m["brody_stub_fallbacks"] == 0
    assert m["brody_errors"] == 0
