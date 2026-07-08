"""Tests — brody_autostart adapter.

Sémantique de liveness :
  - /api/brody/chat ou /brody/chat → POST JSON requis, 2xx + body non vide
  - autres URLs                     → GET, 200/204/405 acceptés
"""
from __future__ import annotations

import http.server
import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from app.adapters import brody_autostart as ba


# ── Serveurs de test ──────────────────────────────────────────────────────────

class _BrodyHandler(http.server.BaseHTTPRequestHandler):
    """Répond 200 + JSON body aux POST, 200 aux GET."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = json.dumps({"text": "ok", "status": "healthy"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


class _GetOnlyHandler(http.server.BaseHTTPRequestHandler):
    """Répond 200 aux GET, 405 aux POST (comme un health endpoint générique)."""

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_POST(self):
        self.send_response(405)
        self.end_headers()

    def log_message(self, *args):
        pass


class _EmptyBodyHandler(http.server.BaseHTTPRequestHandler):
    """Répond 200 aux POST mais avec un body vide (Brody pas prêt)."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


def _start(handler_cls) -> tuple[http.server.HTTPServer, int]:
    server = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, port


# ── _is_brody_chat_url ────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("http://127.0.0.1:8000/api/brody/chat", True),
    ("http://127.0.0.1:8000/brody/chat", True),
    ("http://127.0.0.1:8000/api/brody/chat?foo=1", True),
    ("http://127.0.0.1:8000/api/status", False),
    ("http://127.0.0.1:8000/api/brody/status", False),
    ("", False),
])
def test_is_brody_chat_url(url, expected):
    assert ba._is_brody_chat_url(url) is expected


# ── endpoint_is_live — URL vide ───────────────────────────────────────────────

def test_endpoint_is_live_empty_url():
    assert ba.endpoint_is_live("") is False


# ── endpoint_is_live — Brody chat : POST requis ───────────────────────────────

def test_brody_chat_live_on_post_200_with_body():
    """POST 200 + body non vide → True."""
    server, port = _start(_BrodyHandler)
    try:
        url = f"http://127.0.0.1:{port}/api/brody/chat"
        assert ba.endpoint_is_live(url, timeout_s=2.0) is True
    finally:
        server.shutdown()


def test_brody_chat_405_is_not_live():
    """Un serveur qui répond 405 aux POST sur /api/brody/chat → False.
    (Port ouvert ≠ Brody opérationnel.)"""
    server, port = _start(_GetOnlyHandler)
    try:
        url = f"http://127.0.0.1:{port}/api/brody/chat"
        assert ba.endpoint_is_live(url, timeout_s=2.0) is False
    finally:
        server.shutdown()


def test_brody_chat_200_empty_body_is_not_live():
    """POST 200 mais body vide → False (Brody pas encore prêt)."""
    server, port = _start(_EmptyBodyHandler)
    try:
        url = f"http://127.0.0.1:{port}/api/brody/chat"
        assert ba.endpoint_is_live(url, timeout_s=2.0) is False
    finally:
        server.shutdown()


def test_brody_chat_unreachable_is_not_live():
    assert ba.endpoint_is_live("http://127.0.0.1:19998/api/brody/chat", timeout_s=0.3) is False


def test_brody_chat_path_variant():
    """/brody/chat (sans /api/) est aussi une URL Brody chat."""
    server, port = _start(_BrodyHandler)
    try:
        url = f"http://127.0.0.1:{port}/brody/chat"
        assert ba.endpoint_is_live(url, timeout_s=2.0) is True
    finally:
        server.shutdown()


# ── endpoint_is_live — URL générique : GET accepté ───────────────────────────

def test_generic_health_url_get_200_is_live():
    server, port = _start(_GetOnlyHandler)
    try:
        url = f"http://127.0.0.1:{port}/api/status"
        assert ba.endpoint_is_live(url, timeout_s=2.0) is True
    finally:
        server.shutdown()


def test_generic_health_url_405_is_live():
    """405 sur une URL générique = serveur joignable → True."""
    server, port = _start(_GetOnlyHandler)
    try:
        # On force une URL non-brody-chat qui retourne 405 sur GET
        # En réalité notre handler retourne 200 sur GET ; on mocke HTTPError.
        import urllib.error
        err = urllib.error.HTTPError(url="x", code=405, msg="Method Not Allowed", hdrs=None, fp=None)
        with patch("urllib.request.urlopen", side_effect=err):
            assert ba.endpoint_is_live(f"http://127.0.0.1:{port}/api/status", timeout_s=2.0) is True
    finally:
        server.shutdown()


def test_generic_health_unreachable_is_not_live():
    assert ba.endpoint_is_live("http://127.0.0.1:19997/api/status", timeout_s=0.3) is False


# ── ensure_brody_live — not_configured ───────────────────────────────────────

def test_not_configured_when_no_endpoint(monkeypatch):
    monkeypatch.delenv("BRODY_ENDPOINT", raising=False)
    result = ba.ensure_brody_live(auto_start=False)
    assert result["status"] == "not_configured"
    assert result["live_before"] is False
    assert result["live_after"] is False
    assert result["attempted"] is False


def test_not_configured_when_empty_endpoint(monkeypatch):
    monkeypatch.setenv("BRODY_ENDPOINT", "  ")
    result = ba.ensure_brody_live(auto_start=False)
    assert result["status"] == "not_configured"


# ── ensure_brody_live — missing (endpoint down, pas d'autostart) ──────────────

def test_missing_when_down_no_autostart(monkeypatch):
    monkeypatch.setenv("BRODY_ENDPOINT", "http://127.0.0.1:19996/api/brody/chat")
    monkeypatch.delenv("BRODY_HEALTH_URL", raising=False)
    result = ba.ensure_brody_live(auto_start=False)
    assert result["status"] == "missing"
    assert result["live_before"] is False
    assert result["attempted"] is False


# ── ensure_brody_live — start_command_missing ─────────────────────────────────

def test_start_command_missing_when_no_env(monkeypatch):
    monkeypatch.setenv("BRODY_ENDPOINT", "http://127.0.0.1:19995/api/brody/chat")
    monkeypatch.delenv("BRODY_START_COMMAND", raising=False)
    result = ba.ensure_brody_live(auto_start=True)
    assert result["status"] == "start_command_missing"
    assert result["start_command_present"] is False
    assert result["attempted"] is False


# ── ensure_brody_live — live (déjà actif) ────────────────────────────────────

def test_live_when_brody_post_already_works(monkeypatch):
    """ensure_brody_live → live si le POST /api/brody/chat répond correctement."""
    server, port = _start(_BrodyHandler)
    try:
        url = f"http://127.0.0.1:{port}/api/brody/chat"
        monkeypatch.setenv("BRODY_ENDPOINT", url)
        monkeypatch.setenv("BRODY_HEALTH_URL", url)
        result = ba.ensure_brody_live(auto_start=False)
        assert result["status"] == "live"
        assert result["live_before"] is True
        assert result["live_after"] is True
        assert result["attempted"] is False
    finally:
        server.shutdown()


def test_not_live_when_only_port_open_no_brody_post(monkeypatch):
    """Port ouvert mais POST /api/brody/chat → 405 : status=missing, pas live."""
    server, port = _start(_GetOnlyHandler)
    try:
        url = f"http://127.0.0.1:{port}/api/brody/chat"
        monkeypatch.setenv("BRODY_ENDPOINT", url)
        monkeypatch.setenv("BRODY_HEALTH_URL", url)
        result = ba.ensure_brody_live(auto_start=False)
        assert result["status"] == "missing"
        assert result["live_before"] is False
    finally:
        server.shutdown()


# ── ensure_brody_live — Popen mocké, polling ─────────────────────────────────

def test_popen_called_when_start_command_set(monkeypatch):
    """Popen est appelé avec la commande ; polling stubbed → started_live."""
    monkeypatch.setenv("BRODY_ENDPOINT", "http://127.0.0.1:19994/api/brody/chat")
    monkeypatch.setenv("BRODY_START_COMMAND", "echo mock_start")
    monkeypatch.setenv("BRODY_START_TIMEOUT_S", "2")

    mock_popen = MagicMock()
    call_count = [0]

    def _fake_is_live(url, timeout_s=None):
        if not url or url.strip() in ("", "(not set)"):
            return False
        call_count[0] += 1
        return call_count[0] >= 2  # live au 2e sondage

    with patch("app.adapters.brody_autostart.subprocess.Popen", mock_popen), \
         patch("app.adapters.brody_autostart.endpoint_is_live", side_effect=_fake_is_live), \
         patch("app.adapters.brody_autostart.time.sleep"):
        result = ba.ensure_brody_live(auto_start=True)

    mock_popen.assert_called_once_with("echo mock_start", shell=True)
    assert result["attempted"] is True
    assert result["started"] is True
    assert result["status"] == "started_live"
    assert result["live_after"] is True


def test_start_failed_when_post_never_succeeds(monkeypatch):
    """Popen lancé mais le POST Brody ne répond jamais → start_failed."""
    monkeypatch.setenv("BRODY_ENDPOINT", "http://127.0.0.1:19993/api/brody/chat")
    monkeypatch.setenv("BRODY_START_COMMAND", "echo mock_noop")
    monkeypatch.setenv("BRODY_START_TIMEOUT_S", "1")

    mock_popen = MagicMock()

    def _always_down(url, timeout_s=None):
        return False

    with patch("app.adapters.brody_autostart.subprocess.Popen", mock_popen), \
         patch("app.adapters.brody_autostart.endpoint_is_live", side_effect=_always_down), \
         patch("app.adapters.brody_autostart.time.sleep"), \
         patch("app.adapters.brody_autostart.time.perf_counter", side_effect=[0.0, 0.5, 1.5]):
        result = ba.ensure_brody_live(auto_start=True)

    assert result["status"] == "start_failed"
    assert result["live_after"] is False
    assert result["error"] is not None


# ── Toutes les clés requises toujours présentes ───────────────────────────────

_REQUIRED_KEYS = {
    "attempted", "started", "live_before", "live_after",
    "start_command_present", "status", "error", "endpoint", "health_url",
}


@pytest.mark.parametrize("endpoint,auto_start", [
    (None, False),
    ("http://127.0.0.1:19992/api/brody/chat", False),
    ("http://127.0.0.1:19992/api/brody/chat", True),
])
def test_result_always_has_required_keys(monkeypatch, endpoint, auto_start):
    if endpoint:
        monkeypatch.setenv("BRODY_ENDPOINT", endpoint)
    else:
        monkeypatch.delenv("BRODY_ENDPOINT", raising=False)
    monkeypatch.delenv("BRODY_START_COMMAND", raising=False)
    result = ba.ensure_brody_live(auto_start=auto_start)
    missing = _REQUIRED_KEYS - set(result)
    assert not missing, f"result missing keys: {missing}"


# ── BRODY_HEALTH_URL override ─────────────────────────────────────────────────

def test_health_url_brody_chat_used_for_post(monkeypatch):
    """Si BRODY_HEALTH_URL est une URL brody/chat, le POST est utilisé."""
    server, port = _start(_BrodyHandler)
    try:
        health = f"http://127.0.0.1:{port}/api/brody/chat"
        monkeypatch.setenv("BRODY_ENDPOINT", "http://127.0.0.1:19991/api/brody/chat")
        monkeypatch.setenv("BRODY_HEALTH_URL", health)
        result = ba.ensure_brody_live(auto_start=False)
        assert result["status"] == "live"
        assert result["health_url"] == health
    finally:
        server.shutdown()


def test_health_url_generic_used_for_get(monkeypatch):
    """Si BRODY_HEALTH_URL est une URL générique, GET est utilisé."""
    server, port = _start(_GetOnlyHandler)
    try:
        health = f"http://127.0.0.1:{port}/api/status"
        monkeypatch.setenv("BRODY_ENDPOINT", "http://127.0.0.1:19990/api/brody/chat")
        monkeypatch.setenv("BRODY_HEALTH_URL", health)
        result = ba.ensure_brody_live(auto_start=False)
        assert result["status"] == "live"
        assert result["health_url"] == health
    finally:
        server.shutdown()
