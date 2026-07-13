"""Unit tests for app/adapters/qwen_local.py.

No llama-server required — HTTP calls are patched at urllib.request level.
"""
from __future__ import annotations

import json
import os
import unittest
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.adapters import qwen_local


# ── helpers ───────────────────────────────────────────────────────────────────

def _fake_resp(text: str, model: str = "qwen", finish: str = "stop",
               completion_tokens: int = 4) -> MagicMock:
    body = json.dumps({
        "choices": [{"message": {"content": text}, "finish_reason": finish}],
        "usage": {"completion_tokens": completion_tokens, "total_tokens": completion_tokens + 1},
    }).encode("utf-8")
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _url_error(msg: str = "connection refused") -> urllib.error.URLError:
    return urllib.error.URLError(msg)


# ── category detection ────────────────────────────────────────────────────────

class TestDetectCategory(unittest.TestCase):

    def _d(self, prompt: str) -> str:
        return qwen_local._detect_category(prompt)

    def test_sentiment_pos_neg_neutral(self):
        self.assertEqual(self._d("Classify as positive, negative, or neutral."), "sentiment")

    def test_sentiment_is_positive(self):
        self.assertEqual(self._d("The review 'Worst purchase ever' is: positive, negative, or neutral?"), "sentiment")

    def test_summary_one_sentence(self):
        self.assertEqual(self._d("Summarize in one sentence: 'Solar panels...'"), "summary")

    def test_summary_summarise(self):
        self.assertEqual(self._d("Summarise in one sentence: 'text'"), "summary")

    def test_summary_one_sentence_summary(self):
        self.assertEqual(self._d("Provide a one-sentence summary: 'text'"), "summary")

    def test_factual_capital(self):
        self.assertEqual(self._d("What is the capital of Brazil?"), "factual")

    def test_factual_germany(self):
        self.assertEqual(self._d("The capital city of germany is?"), "factual")

    def test_factual_vatican(self):
        self.assertEqual(self._d("What is the capital of Vatican City?"), "factual")


# ── loopback enforcement ──────────────────────────────────────────────────────

class TestLoopbackEnforcement(unittest.TestCase):

    def test_non_loopback_rejected(self):
        with patch.dict(os.environ, {"QWEN_LOCAL_ENDPOINT": "http://api.fireworks.ai/v1"}):
            result = qwen_local.chat("test")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_available")
        self.assertIn("not loopback", result["error"])

    def test_external_ip_rejected(self):
        with patch.dict(os.environ, {"QWEN_LOCAL_ENDPOINT": "http://8.8.8.8:8080/v1"}):
            result = qwen_local.chat("test")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_available")

    def test_localhost_accepted(self):
        with patch.dict(os.environ, {"QWEN_LOCAL_ENDPOINT": "http://localhost:8080/v1"}):
            with patch("urllib.request.urlopen", return_value=_fake_resp("Berlin")):
                result = qwen_local.chat("Capital of Germany?")
        self.assertTrue(result["success"])


# ── successful calls ──────────────────────────────────────────────────────────

class TestSuccessfulCalls(unittest.TestCase):

    def _call(self, prompt: str, text: str = "negative", **kw) -> dict:
        with patch("urllib.request.urlopen", return_value=_fake_resp(text)):
            return qwen_local.chat(prompt, **kw)

    def test_provider_tagged(self):
        r = self._call("Classify as positive, negative, or neutral.")
        self.assertEqual(r["provider"], "qwen_local")

    def test_success_true(self):
        r = self._call("What is the capital of Brazil?", text="Brasília")
        self.assertTrue(r["success"])
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["text"], "Brasília")
        self.assertIsNone(r["error"])

    def test_text_is_stripped(self):
        r = self._call("What?", text="  Berlin  ")
        self.assertEqual(r["text"], "Berlin")

    def test_elapsed_ms_present(self):
        r = self._call("What?")
        self.assertIsInstance(r["elapsed_ms"], float)
        self.assertGreaterEqual(r["elapsed_ms"], 0.0)

    def test_local_model_tokens(self):
        with patch("urllib.request.urlopen", return_value=_fake_resp("negative", completion_tokens=3)):
            r = qwen_local.chat("is: positive, negative, or neutral?")
        # completion_tokens=3 is in usage; total_tokens=4
        self.assertIsNotNone(r["local_model_tokens"])


# ── error paths ───────────────────────────────────────────────────────────────

class TestErrorPaths(unittest.TestCase):

    def test_connection_refused(self):
        with patch("urllib.request.urlopen", side_effect=_url_error("connection refused")):
            r = qwen_local.chat("test")
        self.assertFalse(r["success"])
        self.assertEqual(r["status"], "not_available")
        self.assertIsNotNone(r["error"])

    def test_timeout(self):
        with patch("urllib.request.urlopen", side_effect=_url_error("timed out")):
            r = qwen_local.chat("test")
        self.assertFalse(r["success"])
        self.assertEqual(r["status"], "timeout")

    def test_empty_choices(self):
        body = json.dumps({"choices": []}).encode("utf-8")
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=resp):
            r = qwen_local.chat("test")
        self.assertFalse(r["success"])
        self.assertEqual(r["status"], "invalid_response")

    def test_empty_content(self):
        with patch("urllib.request.urlopen", return_value=_fake_resp("   ")):
            r = qwen_local.chat("test")
        self.assertFalse(r["success"])
        self.assertEqual(r["status"], "invalid_response")


# ── answer_kind max_tokens routing ────────────────────────────────────────────

class TestMaxTokensRouting(unittest.TestCase):
    """Verify that answer_kind influences the max_tokens in the request body."""

    def _capture_body(self, prompt: str, answer_kind: str) -> dict:
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _fake_resp("ok")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            qwen_local.chat(prompt, answer_kind=answer_kind)
        return captured.get("body", {})

    def test_sentiment_max_tokens(self):
        body = self._capture_body("pos/neg/neutral?", "sentiment")
        self.assertEqual(body["max_tokens"], 8)

    def test_summary_max_tokens(self):
        body = self._capture_body("summarize", "summary")
        self.assertEqual(body["max_tokens"], 96)

    def test_code_file_max_tokens(self):
        body = self._capture_body("code file", "code_file")
        self.assertEqual(body["max_tokens"], 256)


# ── is_available ──────────────────────────────────────────────────────────────

class TestIsAvailable(unittest.TestCase):

    def test_not_available_on_connection_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            self.assertFalse(qwen_local.is_available())

    def test_available_when_200(self):
        resp = MagicMock()
        resp.status = 200
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=resp):
            self.assertTrue(qwen_local.is_available())


if __name__ == "__main__":
    unittest.main()
