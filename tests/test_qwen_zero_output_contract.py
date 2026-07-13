"""Tests for the output contract compliance of Qwen Zero answers.

Verifies that the track1_answer() projection, project_official_row() output,
and answer schema are correct for QWEN_ZERO resolved tasks.
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
        "usage": {"completion_tokens": 4, "total_tokens": 6},
    }).encode("utf-8")
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


_QWEN_ZERO_ENV = {
    "TRACK1_QWEN_ZERO": "1",
    "TRACK1_LOCAL_MODE": "ZERO",
    "FIREWORKS_API_KEY": "dummy_injected_key",
    "FIREWORKS_BASE_URL": "http://127.0.0.1:9",
}


class TestProjectOfficialRow(unittest.TestCase):
    """project_official_row must produce {"task_id", "answer"} only."""

    def _run(self, task_id: str, prompt: str, qwen_answer: str) -> dict:
        with patch.dict(os.environ, _QWEN_ZERO_ENV):
            with patch("urllib.request.urlopen", return_value=_qwen_resp(qwen_answer)):
                from benchmarks.official_resolver import (
                    resolve_task, project_official_row, RuntimeContext
                )
                ctx = RuntimeContext()
                res = resolve_task({"task_id": task_id, "request": prompt}, ctx)
                return project_official_row(res)

    def test_keys_are_task_id_and_answer(self):
        row = self._run("f05", "What is the capital of Brazil?", "Brasília")
        self.assertEqual(set(row.keys()), {"task_id", "answer"})

    def test_task_id_is_preserved(self):
        row = self._run("su01", "Summarize in one sentence: 'Solar panels...'", "Solar panels convert sunlight.")
        self.assertEqual(row["task_id"], "su01")

    def test_answer_is_qwen_text(self):
        row = self._run("f05", "What is the capital of Brazil?", "Brasília")
        self.assertIn("Brasília", row["answer"])

    def test_answer_not_route_tag(self):
        row = self._run("f05", "What is the capital of Brazil?", "Brasília")
        self.assertNotIn("Route:", row["answer"])

    def test_answer_not_qwen_zero_tag(self):
        row = self._run("f05", "What is the capital of Brazil?", "Brasília")
        self.assertNotIn("[qwen_zero]", row["answer"])

    def test_answer_not_dry_run(self):
        row = self._run("f05", "What is the capital of Brazil?", "Brasília")
        self.assertNotIn("[dry-run]", row["answer"])

    def test_answer_not_empty(self):
        row = self._run("f14", "Answer in one word: capital of Germany?", "Berlin")
        self.assertTrue(row["answer"].strip())


class TestTrack1AnswerContract(unittest.TestCase):
    """track1_answer() must return the Qwen text, not a route-stub."""

    def test_track1_answer_returns_output_not_route_stub(self):
        from benchmarks.track1_runner import track1_answer
        row = {
            "id": "test",
            "request": "What is the capital?",
            "actual_route": "local_solver",
            "intent_type": "question",
            "missing": [],
            "gate_matched": None,
            "output": "Berlin",
            "memory_entry": None,
            "topic_name": "general",
        }
        answer = track1_answer(row)
        self.assertEqual(answer, "Berlin")

    def test_track1_answer_not_route_qwen_local(self):
        """If route="qwen_local" were passed, track1_answer would return wrong answer."""
        from benchmarks.track1_runner import track1_answer
        row = {
            "id": "test",
            "request": "test",
            "actual_route": "qwen_local",  # this is the WRONG route to use
            "intent_type": "question",
            "missing": [],
            "gate_matched": None,
            "output": "Berlin",
            "memory_entry": None,
            "topic_name": "general",
        }
        answer = track1_answer(row)
        # "qwen_local" falls through to f"Route: {route}." — WRONG behavior
        # This test documents why we MUST use "local_solver" as the route
        self.assertEqual(answer, "Route: qwen_local.")


class TestAnswerSchemaAllTasks(unittest.TestCase):
    """Batch test: all 17 failing task prompts must produce non-empty answers."""

    _TASKS = [
        ("f05", "What is the capital of Brazil?", "Brasília"),
        ("f10", "The capital city of germany is?", "Berlin"),
        ("f14", "Answer in one word: capital of Germany?", "Berlin"),
        ("f15", "What is the capital of the largest country by area?", "Moscow"),
        ("f16", "What is the capital of Vatican City?", "Vatican City"),
        ("s06", "The review 'Worst purchase ever' is: positive, negative, or neutral?", "negative"),
        ("s12", "In one word (positive/negative/neutral): 'This ruined my day.'", "negative"),
        ("s13", "Classify as positive, negative, or neutral: 'Great concept, poor execution.'", "negative"),
        ("su01", "Summarize in one sentence: 'Solar panels convert sunlight into electricity using photovoltaic cells.'",
         "Solar panels use photovoltaic cells to convert sunlight into electricity."),
        ("su12", "Summarize in one sentence.", "The text does not contain specific content to summarize."),
    ]

    def test_all_produce_non_empty_answers(self):
        for task_id, prompt, qwen_answer in self._TASKS:
            with self.subTest(task_id=task_id):
                with patch.dict(os.environ, _QWEN_ZERO_ENV):
                    with patch("urllib.request.urlopen", return_value=_qwen_resp(qwen_answer)):
                        from benchmarks.official_resolver import (
                            project_official_row, resolve_task, RuntimeContext
                        )
                        ctx = RuntimeContext()
                        res = resolve_task({"task_id": task_id, "request": prompt}, ctx)
                        row = project_official_row(res)
                self.assertTrue(row["answer"].strip(), f"{task_id}: answer is empty")

    def test_all_produce_zero_remote_tokens(self):
        for task_id, prompt, qwen_answer in self._TASKS:
            with self.subTest(task_id=task_id):
                with patch.dict(os.environ, _QWEN_ZERO_ENV):
                    with patch("urllib.request.urlopen", return_value=_qwen_resp(qwen_answer)):
                        from benchmarks.official_resolver import resolve_task, RuntimeContext
                        ctx = RuntimeContext()
                        res = resolve_task({"task_id": task_id, "request": prompt}, ctx)
                self.assertEqual(
                    res.get("total_tokens", 0), 0,
                    f"{task_id}: total_tokens={res.get('total_tokens')} must be 0",
                )


if __name__ == "__main__":
    unittest.main()
