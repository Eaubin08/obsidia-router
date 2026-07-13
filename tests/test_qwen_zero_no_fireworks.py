"""Anti-Fireworks tests for TRACK1_QWEN_ZERO=1 mode.

Verifies:
  - fireworks.chat() is NEVER called in QWEN_ZERO mode
  - FIREWORKS_TOKENS = 0 across all resolution paths
  - Monkey-patch is always restored after run_one()
  - A real socket to FIREWORKS_BASE_URL is never attempted
"""
from __future__ import annotations

import json
import os
import socket
import sys
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.metrics.collector import MetricsCollector
import app.adapters.fireworks as fw_module


def _qwen_resp(text: str = "negative") -> MagicMock:
    body = json.dumps({
        "choices": [{"message": {"content": text}}],
        "usage": {"completion_tokens": 1, "total_tokens": 2},
    }).encode("utf-8")
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestFireworksNeverCalled(unittest.TestCase):
    """Ensure fireworks.chat() is NEVER invoked when TRACK1_QWEN_ZERO=1."""

    def setUp(self):
        self._fw_call_count = 0
        self._original_fw_chat = fw_module.chat

    def tearDown(self):
        fw_module.chat = self._original_fw_chat

    def _counting_blocker(self, model, prompt_text, **kwargs):
        self._fw_call_count += 1
        return {
            "text": "[test] fireworks.chat was called — FORBIDDEN in QWEN_ZERO",
            "total_tokens": 99,
        }

    def test_fireworks_not_called_for_sentiment(self):
        """Sentiment tasks escalate to Qwen, not Fireworks."""
        fw_module.chat = self._counting_blocker
        env = {
            "TRACK1_QWEN_ZERO": "1",
            "TRACK1_LOCAL_MODE": "ZERO",
            "FIREWORKS_API_KEY": "dummy_injected_key",
            "FIREWORKS_BASE_URL": "http://127.0.0.1:9",
            "ALLOWED_MODELS": "accounts/fireworks/models/gpt-oss-120b",
        }
        with patch.dict(os.environ, env):
            with patch("urllib.request.urlopen", return_value=_qwen_resp("negative")):
                from app.cli import run_one
                metrics = MetricsCollector()
                try:
                    run_one(
                        "Classify as positive, negative, or neutral: 'Worst purchase ever'",
                        metrics, {}, None,
                    )
                except Exception:
                    pass
        self.assertEqual(
            self._fw_call_count, 0,
            f"fireworks.chat() was called {self._fw_call_count} time(s) in QWEN_ZERO mode — FORBIDDEN",
        )

    def test_fireworks_not_called_for_factual(self):
        """Factual tasks that need escalation → Qwen, not Fireworks."""
        fw_module.chat = self._counting_blocker
        env = {
            "TRACK1_QWEN_ZERO": "1",
            "TRACK1_LOCAL_MODE": "ZERO",
            "FIREWORKS_API_KEY": "dummy_injected_key",
        }
        with patch.dict(os.environ, env):
            with patch("urllib.request.urlopen", return_value=_qwen_resp("Brasília")):
                from app.cli import run_one
                metrics = MetricsCollector()
                try:
                    run_one("What is the capital of Brazil?", metrics, {}, None)
                except Exception:
                    pass
        self.assertEqual(
            self._fw_call_count, 0,
            f"fireworks.chat() was called {self._fw_call_count} time(s) — FORBIDDEN",
        )

    def test_monkey_patch_restored_after_run_one(self):
        """The monkey-patch must be cleaned up even if run_one raises."""
        original_chat = fw_module.chat
        env = {
            "TRACK1_QWEN_ZERO": "1",
            "TRACK1_LOCAL_MODE": "ZERO",
        }
        with patch.dict(os.environ, env):
            with patch("urllib.request.urlopen", side_effect=OSError("refused")):
                from benchmarks.official_resolver import resolve_task, RuntimeContext
                ctx = RuntimeContext()
                try:
                    resolve_task({"task_id": "t1", "request": "What capital?"}, ctx)
                except Exception:
                    pass
        self.assertIs(
            fw_module.chat, original_chat,
            "fireworks.chat was NOT restored after resolve_task — patch leaked",
        )


class TestZeroTokens(unittest.TestCase):
    """Verify FIREWORKS_TOKENS = 0 for all Qwen-resolved tasks."""

    def test_no_fireworks_tokens_in_resolution(self):
        env = {
            "TRACK1_QWEN_ZERO": "1",
            "TRACK1_LOCAL_MODE": "ZERO",
            "FIREWORKS_API_KEY": "dummy_injected_key",
            "FIREWORKS_BASE_URL": "http://127.0.0.1:9",
        }
        with patch.dict(os.environ, env):
            with patch("urllib.request.urlopen", return_value=_qwen_resp("Brasília")):
                from benchmarks.official_resolver import resolve_task, RuntimeContext
                ctx = RuntimeContext()
                result = resolve_task({"task_id": "f05", "request": "What is the capital of Brazil?"}, ctx)

        self.assertEqual(
            result.get("total_tokens", 0), 0,
            f"total_tokens={result.get('total_tokens')} — must be 0 in QWEN_ZERO mode",
        )
        self.assertEqual(
            result.get("remote_calls", 0), 0,
            f"remote_calls={result.get('remote_calls')} — must be 0 in QWEN_ZERO mode",
        )

    def test_no_socket_to_dummy_base_url(self):
        """A real socket connection to 127.0.0.1:9 must NEVER be attempted."""
        connections: list[tuple] = []
        _orig_connect = socket.socket.connect

        def _spy_connect(self_sock, addr):
            if isinstance(addr, tuple) and addr[0] == "127.0.0.1" and addr[1] == 9:
                connections.append(addr)
            return _orig_connect(self_sock, addr)

        env = {
            "TRACK1_QWEN_ZERO": "1",
            "TRACK1_LOCAL_MODE": "ZERO",
            "FIREWORKS_API_KEY": "dummy_injected_key",
            "FIREWORKS_BASE_URL": "http://127.0.0.1:9",
            "ALLOWED_MODELS": "accounts/fireworks/models/gpt-oss-120b",
        }
        with patch.dict(os.environ, env):
            with patch.object(socket.socket, "connect", _spy_connect):
                with patch("urllib.request.urlopen", return_value=_qwen_resp("negative")):
                    from benchmarks.official_resolver import resolve_task, RuntimeContext
                    ctx = RuntimeContext()
                    try:
                        resolve_task(
                            {"task_id": "s06", "request": "The review 'Worst purchase ever' is: positive, negative, or neutral?"},
                            ctx,
                        )
                    except Exception:
                        pass

        self.assertEqual(
            connections, [],
            f"Socket connection to 127.0.0.1:9 was attempted: {connections}",
        )


if __name__ == "__main__":
    unittest.main()
