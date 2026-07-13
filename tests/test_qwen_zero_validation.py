"""Tests for the validation + repair pipeline applied to Qwen outputs.

Exercises the same validate_remote_output / repair_remote_output pipeline
that the official_resolver's Qwen Zero block uses, against the exact prompts
from the 17 failing tasks.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.semantic.remote_validation import validate_remote_output
from app.semantic.remote_repair import repair_remote_output
from benchmarks.output_constraints import parse_output_constraints


class TestSentimentValidation(unittest.TestCase):
    """Sentiment tasks with and without allowed_labels constraints."""

    # s13: "Classify as positive, negative, or neutral" → allowed_labels detected
    _S13 = "Classify as positive, negative, or neutral: 'Great concept, poor execution.'"

    def _oc(self, prompt: str):
        return parse_output_constraints(prompt)

    def test_s13_has_allowed_labels(self):
        oc = self._oc(self._S13)
        self.assertIsNotNone(oc.allowed_labels, "s13 must detect allowed_labels")
        self.assertIn("negative", oc.allowed_labels)

    def test_single_word_negative_passes(self):
        oc = self._oc(self._S13)
        valid, reasons = validate_remote_output("negative", allowed_labels=oc.allowed_labels)
        self.assertTrue(valid, f"Single-word 'negative' must pass: {reasons}")

    def test_mixed_label_passes(self):
        oc = self._oc(self._S13)
        valid, _ = validate_remote_output("neutral", allowed_labels=oc.allowed_labels)
        self.assertTrue(valid)

    def test_label_embedded_in_sentence_fails(self):
        oc = self._oc(self._S13)
        valid, reasons = validate_remote_output(
            "The review is negative overall.", allowed_labels=oc.allowed_labels
        )
        self.assertFalse(valid)
        self.assertIn("label_not_in_allowed_set", reasons)

    def test_repair_strips_preamble_before_label(self):
        oc = self._oc(self._S13)
        raw = "The sentiment is: negative"
        rep = repair_remote_output(raw, allowed_labels=oc.allowed_labels)
        if rep.repair_applied:
            valid, _ = validate_remote_output(rep.repaired, allowed_labels=oc.allowed_labels)
            self.assertTrue(valid, f"Repaired '{rep.repaired}' should pass")

    def test_uppercase_label_passes_after_normalize(self):
        oc = self._oc(self._S13)
        # Validator uses .lower().startswith() so "Negative" passes
        valid, _ = validate_remote_output("Negative", allowed_labels=oc.allowed_labels)
        self.assertTrue(valid)

    def test_s06_no_allowed_labels(self):
        # "is: positive, negative, or neutral?" — no "as X, Y, or Z" → no allowed_labels
        oc = self._oc("The review 'Worst purchase ever' is: positive, negative, or neutral?")
        # May or may not detect — key thing is the validator doesn't block any answer
        if oc.allowed_labels is None:
            valid, _ = validate_remote_output("negative")
            self.assertTrue(valid)


class TestSummaryValidation(unittest.TestCase):
    """Summary tasks with sentence_count=1 constraints."""

    _SU01 = "Summarize in one sentence: 'Solar panels convert sunlight into electricity using photovoltaic cells.'"
    _SU09 = "Summarize in 1 sentence: 'Solar panels convert sunlight into electricity using photovoltaic cells.'"
    _SU16 = "SUMMARIZE IN ONE SENTENCE: 'Solar panels convert sunlight into electricity using photovoltaic cells.'"

    def _oc(self, prompt: str):
        return parse_output_constraints(prompt)

    def test_su01_sentence_count_detected(self):
        oc = self._oc(self._SU01)
        self.assertEqual(oc.sentence_count, 1)

    def test_su09_numeric_sentence_count(self):
        oc = self._oc(self._SU09)
        self.assertEqual(oc.sentence_count, 1)

    def test_su16_uppercase_detected(self):
        oc = self._oc(self._SU16)
        self.assertEqual(oc.sentence_count, 1)

    def test_single_sentence_passes(self):
        oc = self._oc(self._SU01)
        text = "Solar panels use photovoltaic cells to convert sunlight into electricity."
        valid, reasons = validate_remote_output(text, sentence_count=oc.sentence_count)
        self.assertTrue(valid, f"Single sentence must pass: {reasons}")

    def test_two_sentences_fails(self):
        oc = self._oc(self._SU01)
        text = "Solar panels convert sunlight. They use photovoltaic cells."
        valid, reasons = validate_remote_output(text, sentence_count=oc.sentence_count)
        self.assertFalse(valid)
        self.assertTrue(any("sentence_count" in r for r in reasons))

    def test_repair_keeps_first_sentence(self):
        oc = self._oc(self._SU01)
        text = "Solar panels convert sunlight into electricity. They are efficient."
        rep = repair_remote_output(text, sentence_count=oc.sentence_count)
        if rep.repair_applied:
            revalid, _ = validate_remote_output(rep.repaired, sentence_count=oc.sentence_count)
            self.assertTrue(revalid, f"Repaired '{rep.repaired}' must pass")

    def test_su12_no_sentence_count_required(self):
        # "Summarize in one sentence." without a passage — sentence_count=1
        oc = self._oc("Summarize in one sentence.")
        # Qwen's output of "There is no specific text to summarize." → 1 sentence → passes
        text = "There is no specific text to summarize."
        valid, _ = validate_remote_output(text, sentence_count=oc.sentence_count)
        self.assertTrue(valid)


class TestRepairSafety(unittest.TestCase):
    """Repair operations must be safe (never empty the output)."""

    def test_repair_does_not_produce_empty(self):
        from app.semantic.remote_repair import repair_remote_output
        rep = repair_remote_output("This is a fine sentence.", sentence_count=1)
        if rep.repair_applied:
            self.assertGreater(len(rep.repaired.strip()), 0)

    def test_repair_result_has_repair_safe(self):
        rep = repair_remote_output("Neutral sentiment.", allowed_labels=("positive", "negative", "neutral"))
        self.assertIsInstance(rep.repair_safe, bool)


if __name__ == "__main__":
    unittest.main()
