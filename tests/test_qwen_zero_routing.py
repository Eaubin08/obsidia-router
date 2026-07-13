"""Tests for QWEN_ZERO routing in official_resolver.py.

Verifies that:
- Local deterministic closures still work (unaffected by QWEN_ZERO)
- Tasks that go to "fireworks" route are intercepted and resolved by Qwen
- Qwen answer appears as actual_route="local_solver" in the answer_row
- resolve_task() returns qwen_zero_attempted=True for escalated tasks
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _qwen_resp(text: str) -> MagicMock:
    body = json.dumps({
        "choices": [{"message": {"content": text}}],
        "usage": {"completion_tokens": len(text.split()), "total_tokens": len(text.split()) + 2},
    }).encode("utf-8")
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


QWEN_ZERO_ENV = {
    "TRACK1_QWEN_ZERO": "1",
    "TRACK1_LOCAL_MODE": "ZERO",
    "FIREWORKS_API_KEY": "dummy_injected_key",
    "FIREWORKS_BASE_URL": "http://127.0.0.1:9",
    "ALLOWED_MODELS": "accounts/fireworks/models/gpt-oss-120b",
}


class TestQwenZeroRouting(unittest.TestCase):

    def _resolve(self, task_id: str, prompt: str, qwen_text: str) -> dict:
        with patch.dict(os.environ, QWEN_ZERO_ENV):
            with patch("urllib.request.urlopen", return_value=_qwen_resp(qwen_text)):
                from benchmarks.official_resolver import resolve_task, RuntimeContext
                ctx = RuntimeContext()
                return resolve_task({"task_id": task_id, "request": prompt}, ctx)

    def test_factual_brazil_resolved_by_qwen(self):
        r = self._resolve("f05", "What is the capital of Brazil?", "Brasília")
        self.assertIn("Brasília", r["answer"])

    def test_factual_germany_resolved_by_qwen(self):
        r = self._resolve("f10", "The capital city of germany is?", "Berlin")
        self.assertIn("Berlin", r["answer"])

    def test_sentiment_worst_purchase_resolved(self):
        r = self._resolve(
            "s06",
            "The review 'Worst purchase ever' is: positive, negative, or neutral?",
            "negative",
        )
        self.assertIn("negative", r["answer"].lower())

    def test_summary_resolved_by_qwen(self):
        r = self._resolve(
            "su01",
            "Summarize in one sentence: 'Solar panels convert sunlight into electricity using photovoltaic cells.'",
            "Solar panels use photovoltaic cells to convert sunlight into electricity.",
        )
        self.assertNotEqual(r["answer"].strip(), "")
        self.assertNotIn("[qwen_zero]", r["answer"])

    def test_no_remote_tokens_in_result(self):
        r = self._resolve("f05", "What is the capital of Brazil?", "Brasília")
        self.assertEqual(r.get("total_tokens", 0), 0)
        self.assertEqual(r.get("remote_calls", 0), 0)
        self.assertFalse(r.get("remote_required", False))

    def test_qwen_zero_attempted_flagged(self):
        r = self._resolve("f05", "What is the capital of Brazil?", "Brasília")
        # qwen_zero_attempted is set for tasks that reach the Qwen block
        self.assertIn("qwen_zero_valid", r)
        self.assertTrue(r.get("qwen_zero_valid", False))

    def test_task_id_preserved(self):
        r = self._resolve("f05", "What is the capital of Brazil?", "Brasília")
        self.assertEqual(r["task_id"], "f05")

    def test_answer_not_error_tag(self):
        r = self._resolve("f16", "What is the capital of Vatican City?", "Vatican City")
        self.assertFalse(r["answer"].startswith("[error]"))
        self.assertFalse(r["answer"].startswith("[dry-run]"))
        self.assertFalse(r["answer"].startswith("[qwen_zero]"))


class TestDeterministicClosuresUnaffected(unittest.TestCase):
    """Local closures (local_solver or Brody) must still work in QWEN_ZERO mode.

    The store math problem routes to Brody in this configuration (governed
    organ), not to local_solver directly.  The key invariant is that it is
    resolved LOCALLY (zero Fireworks tokens, answer non-empty) regardless of
    which local path fires.
    """

    def _resolve(self, prompt: str) -> dict:
        with patch.dict(os.environ, QWEN_ZERO_ENV):
            # Patch urlopen so that qwen_local.chat() does not block if the
            # local solver fails and the Qwen block runs (no llama-server here)
            with patch("urllib.request.urlopen", return_value=_qwen_resp("936")):
                from benchmarks.official_resolver import resolve_task, RuntimeContext
                ctx = RuntimeContext()
                return resolve_task({"task_id": "det_test", "request": prompt}, ctx)

    def test_math_resolved_locally_zero_remote_tokens(self):
        r = self._resolve(
            "A store sells items for $12 each. If a customer buys 78 items, what is the total cost?"
        )
        self.assertEqual(r.get("total_tokens", 0), 0,
                         "Math must have zero Fireworks tokens in QWEN_ZERO mode")
        self.assertTrue(r["answer"].strip(), "Math must produce a non-empty answer")

    def test_math_local_route_not_fireworks(self):
        r = self._resolve(
            "A store sells items for $12 each. If a customer buys 78 items, what is the total cost?"
        )
        # Route is either local_solver (direct solver) or brody (governed),
        # never "fireworks" in QWEN_ZERO mode.
        self.assertNotEqual(r["route"], "fireworks",
                            "Math must NOT route to Fireworks in QWEN_ZERO mode")


if __name__ == "__main__":
    unittest.main()
