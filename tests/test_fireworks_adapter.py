"""Tests — fireworks adapter."""
from __future__ import annotations

import json
import threading
import http.server
from unittest.mock import patch

import pytest

from app.adapters.fireworks import chat, extract_text


# ── extract_text ──────────────────────────────────────────────────────────────

def test_standard_content_is_extracted():
    data = {"choices": [{"message": {"content": "hello"}}]}
    assert extract_text(data) == "hello"


def test_reasoning_model_without_content_does_not_crash():
    # gpt-oss style: content missing, reasoning_content present
    data = {"choices": [{"message": {"reasoning_content": "thinking..."}}]}
    assert extract_text(data) == "thinking..."


def test_null_content_falls_back():
    data = {"choices": [{"message": {"content": None}}]}
    assert extract_text(data) == "[empty completion]"


def test_missing_choices_returns_error_text():
    assert extract_text({}) == "[error] no choices in response"
    assert extract_text({"choices": []}) == "[error] no choices in response"


# ── dry-run (no API key) ──────────────────────────────────────────────────────

def test_dry_run_without_api_key(monkeypatch):
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    result = chat("accounts/fireworks/models/gpt-oss-120b", "ping")
    assert result["dry_run"] is True
    assert result["total_tokens"] > 0  # estimated
    assert result["latency_s"] == 0.0


# ── headers envoyés ───────────────────────────────────────────────────────────

def _make_mock_server(response_body: dict, status: int = 200):
    """Serveur HTTP qui capture les headers reçus."""
    captured: list[dict] = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            captured.append(dict(self.headers))
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
    return server, port, captured


_OK_RESPONSE = {
    "choices": [{"message": {"content": "pong"}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
}


def test_request_has_user_agent(monkeypatch):
    """User-Agent doit être 'obsidia-router/track1-benchmark' (fix Cloudflare 403/1010)."""
    server, port, captured = _make_mock_server(_OK_RESPONSE)
    try:
        monkeypatch.setenv("FIREWORKS_API_KEY", "test-key-1234")
        monkeypatch.setenv("FIREWORKS_BASE_URL", f"http://127.0.0.1:{port}")
        chat("accounts/fireworks/models/gpt-oss-120b", "ping", max_tokens=16)
        assert captured, "aucun POST reçu par le serveur mock"
        hdrs = {k.lower(): v for k, v in captured[0].items()}
        assert hdrs.get("user-agent") == "obsidia-router/track1-benchmark", (
            f"User-Agent incorrect: {hdrs.get('user-agent')!r} — "
            "Cloudflare bloque Python-urllib/3.x avec 403/1010"
        )
    finally:
        server.shutdown()


def test_request_has_accept_header(monkeypatch):
    """Accept: application/json doit être présent."""
    server, port, captured = _make_mock_server(_OK_RESPONSE)
    try:
        monkeypatch.setenv("FIREWORKS_API_KEY", "test-key-1234")
        monkeypatch.setenv("FIREWORKS_BASE_URL", f"http://127.0.0.1:{port}")
        chat("accounts/fireworks/models/gpt-oss-120b", "ping", max_tokens=16)
        assert captured
        hdrs = {k.lower(): v for k, v in captured[0].items()}
        assert hdrs.get("accept") == "application/json", (
            f"Accept header incorrect: {hdrs.get('accept')!r}"
        )
    finally:
        server.shutdown()


def test_request_has_content_type(monkeypatch):
    server, port, captured = _make_mock_server(_OK_RESPONSE)
    try:
        monkeypatch.setenv("FIREWORKS_API_KEY", "test-key-1234")
        monkeypatch.setenv("FIREWORKS_BASE_URL", f"http://127.0.0.1:{port}")
        chat("accounts/fireworks/models/gpt-oss-120b", "ping", max_tokens=16)
        assert captured
        hdrs = {k.lower(): v for k, v in captured[0].items()}
        assert "application/json" in hdrs.get("content-type", "")
    finally:
        server.shutdown()


def test_authorization_header_not_in_error_message(monkeypatch):
    """En cas d'erreur, la clé ne doit jamais apparaître dans result['error']."""
    server, port, _ = _make_mock_server({}, status=403)
    try:
        secret_key = "sk-super-secret-key-12345"
        monkeypatch.setenv("FIREWORKS_API_KEY", secret_key)
        monkeypatch.setenv("FIREWORKS_BASE_URL", f"http://127.0.0.1:{port}")
        result = chat("accounts/fireworks/models/gpt-oss-120b", "ping", max_tokens=16)
        assert secret_key not in (result.get("error") or ""), (
            "La clé API ne doit jamais apparaître dans le message d'erreur"
        )
        assert secret_key not in (result.get("text") or "")
    finally:
        server.shutdown()


def test_403_error_has_hint(monkeypatch):
    """Une 403 doit inclure un hint lisible dans le message d'erreur."""
    server, port, _ = _make_mock_server({}, status=403)
    try:
        monkeypatch.setenv("FIREWORKS_API_KEY", "test-key")
        monkeypatch.setenv("FIREWORKS_BASE_URL", f"http://127.0.0.1:{port}")
        result = chat("accounts/fireworks/models/gpt-oss-120b", "ping", max_tokens=16)
        assert "403" in (result.get("error") or "")
        assert result.get("dry_run") is False
    finally:
        server.shutdown()


def test_404_error_has_hint(monkeypatch):
    """Une 404 doit mentionner que le modèle n'est pas disponible."""
    server, port, _ = _make_mock_server({}, status=404)
    try:
        monkeypatch.setenv("FIREWORKS_API_KEY", "test-key")
        monkeypatch.setenv("FIREWORKS_BASE_URL", f"http://127.0.0.1:{port}")
        result = chat("accounts/fireworks/models/llama-v3p1-8b-instruct", "ping", max_tokens=16)
        assert "404" in (result.get("error") or "")
    finally:
        server.shutdown()


def test_successful_call_returns_text_and_tokens(monkeypatch):
    server, port, _ = _make_mock_server(_OK_RESPONSE)
    try:
        monkeypatch.setenv("FIREWORKS_API_KEY", "test-key")
        monkeypatch.setenv("FIREWORKS_BASE_URL", f"http://127.0.0.1:{port}")
        result = chat("accounts/fireworks/models/gpt-oss-120b", "ping", max_tokens=16)
        assert result["text"] == "pong"
        assert result["total_tokens"] == 7
        assert result.get("error") is None
        assert result.get("dry_run") is False
    finally:
        server.shutdown()


def test_payload_includes_temperature_zero(monkeypatch):
    """temperature=0 doit être dans le body (reproductibilité)."""
    captured_body: list[dict] = []

    class _CaptureHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            captured_body.append(json.loads(self.rfile.read(length)))
            body = json.dumps(_OK_RESPONSE).encode()
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
        monkeypatch.setenv("FIREWORKS_API_KEY", "test-key")
        monkeypatch.setenv("FIREWORKS_BASE_URL", f"http://127.0.0.1:{port}")
        chat("accounts/fireworks/models/gpt-oss-120b", "ping", max_tokens=16)
        assert captured_body
        payload = captured_body[0]
        assert payload.get("temperature") == 0.0
        assert payload.get("model") == "accounts/fireworks/models/gpt-oss-120b"
        assert isinstance(payload.get("messages"), list)
    finally:
        server.shutdown()
