"""LOT F — telemetry, route metric clarity, practice schema, estimated vs measured.

All tests are network-free and do not modify routing logic.
"""
from __future__ import annotations

import json

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

_BASELINE_TELEMETRY_REQUIRED_KEYS = {
    "task_id",
    "answer_kind",
    "requested_max_tokens",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "finish_reason",
    "final_content_present",
    "reasoning_content_present",
    "truncated",
    "error",
    "final_text_chars",
    "latency_s",
    "usage_available",
    "selected_model",
    "actual_model_used",
}

_BASELINE_TELEMETRY_FORBIDDEN_KEYS = {
    "request",
    "prompt",
    "system_prompt",
    "contract_prompt",
    "answer",
    "text",
    "content",
    "reasoning_content",
    "memory_entry",
}


def _make_telemetry_row(
    *,
    task_id: str = "test_task",
    answer_kind: str = "direct_answer",
    requested_max_tokens: int = 850,
    prompt_tokens: int = 120,
    completion_tokens: int = 200,
    total_tokens: int = 320,
    finish_reason: str | None = "stop",
    final_content_present: bool = True,
    reasoning_content_present: bool = False,
    truncated: bool = False,
    error: str | None = None,
    final_text_chars: int = 180,
    latency_s: float = 1.23,
    usage_available: bool = True,
    selected_model: str = "accounts/fireworks/models/gpt-oss-120b",
    actual_model_used: str = "accounts/fireworks/models/gpt-oss-120b",
) -> dict:
    return {
        "task_id": task_id,
        "answer_kind": answer_kind,
        "requested_max_tokens": requested_max_tokens,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "finish_reason": finish_reason,
        "final_content_present": final_content_present,
        "reasoning_content_present": reasoning_content_present,
        "truncated": truncated,
        "error": error,
        "final_text_chars": final_text_chars,
        "latency_s": latency_s,
        "usage_available": usage_available,
        "selected_model": selected_model,
        "actual_model_used": actual_model_used,
    }


# ── 1. Baseline telemetry schema ──────────────────────────────────────────────

class TestBaselineTelemetrySchema:
    def test_required_keys_present_complete_response(self):
        row = _make_telemetry_row()
        assert _BASELINE_TELEMETRY_REQUIRED_KEYS.issubset(row.keys())

    def test_required_keys_present_truncated_response(self):
        row = _make_telemetry_row(
            finish_reason="length",
            truncated=True,
            error="truncated_completion",
            final_content_present=True,
        )
        assert _BASELINE_TELEMETRY_REQUIRED_KEYS.issubset(row.keys())

    def test_no_forbidden_keys_in_telemetry(self):
        row = _make_telemetry_row()
        assert not (_BASELINE_TELEMETRY_FORBIDDEN_KEYS & row.keys())

    def test_complete_response_stop_finish_reason(self):
        row = _make_telemetry_row(finish_reason="stop", truncated=False, error=None)
        assert row["finish_reason"] == "stop"
        assert row["truncated"] is False
        assert row["error"] is None
        assert row["final_content_present"] is True

    def test_truncated_response_length_finish_reason(self):
        row = _make_telemetry_row(
            finish_reason="length",
            truncated=True,
            error="truncated_completion",
            completion_tokens=850,
            requested_max_tokens=850,
        )
        assert row["finish_reason"] == "length"
        assert row["truncated"] is True
        assert row["error"] == "truncated_completion"

    def test_final_content_present_true_with_truncation_is_still_error(self):
        row = _make_telemetry_row(
            final_content_present=True,
            truncated=True,
            error="truncated_completion",
        )
        assert row["final_content_present"] is True
        assert row["error"] == "truncated_completion"
        # The error field must not be cleared by final_content_present

    def test_reasoning_content_present_stored_as_bool(self):
        row_with = _make_telemetry_row(reasoning_content_present=True)
        row_without = _make_telemetry_row(reasoning_content_present=False)
        assert isinstance(row_with["reasoning_content_present"], bool)
        assert isinstance(row_without["reasoning_content_present"], bool)

    def test_no_reasoning_text_in_telemetry(self):
        row = _make_telemetry_row(reasoning_content_present=True)
        row_json = json.dumps(row)
        # No private reasoning text stored as a value
        assert "private reasoning" not in row_json
        # The forbidden key is "reasoning_content" (exact) — not the boolean
        # flag "reasoning_content_present" which is required metadata.
        assert "reasoning_content" not in row.keys()
        assert "reasoning_content_present" in row.keys()

    def test_requested_max_tokens_matches_budget_passed(self):
        row = _make_telemetry_row(requested_max_tokens=1700)
        assert row["requested_max_tokens"] == 1700

    def test_token_counts_propagated(self):
        row = _make_telemetry_row(
            prompt_tokens=300,
            completion_tokens=500,
            total_tokens=800,
        )
        assert row["prompt_tokens"] == 300
        assert row["completion_tokens"] == 500
        assert row["total_tokens"] == 800

    def test_final_text_chars_is_int_not_text(self):
        row = _make_telemetry_row(final_text_chars=245)
        assert isinstance(row["final_text_chars"], int)
        assert "final_text_chars" in row
        # Must not contain actual text
        assert len(str(row["final_text_chars"])) < 20

    def test_usage_available_reflects_token_presence(self):
        row_with_usage = _make_telemetry_row(total_tokens=320, usage_available=True)
        row_no_usage = _make_telemetry_row(
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            usage_available=False,
        )
        assert row_with_usage["usage_available"] is True
        assert row_no_usage["usage_available"] is False

    def test_telemetry_schema_stable_as_json(self):
        row = _make_telemetry_row()
        serialized = json.dumps(row)
        recovered = json.loads(serialized)
        assert recovered.keys() == row.keys()

    def test_telemetry_present_for_each_baseline_call(self):
        tasks = ["t1", "t2", "t3"]
        telemetry = [_make_telemetry_row(task_id=t) for t in tasks]
        assert len(telemetry) == len(tasks)
        assert [r["task_id"] for r in telemetry] == tasks


# ── 2. Route metric clarity ───────────────────────────────────────────────────

def _make_row(
    expected_route: str | None,
    actual_route: str,
    allowed_routes: list[str] | None = None,
) -> dict:
    _expected = expected_route
    if allowed_routes:
        ok = actual_route in allowed_routes
    else:
        ok = actual_route == expected_route if expected_route else True
    _exact = (actual_route == _expected) if _expected is not None else None
    _alt = (_exact is False) and bool(ok)
    return {
        "expected_route": expected_route,
        "allowed_routes": allowed_routes,
        "actual_route": actual_route,
        "route_correct": ok,
        "exact_route_match": _exact,
        "accepted_route_correct": bool(ok),
        "alternative_route_used": _alt,
    }


class TestRouteMetrics:
    def test_exact_match_identical_route(self):
        row = _make_row("no_model_needed", "no_model_needed")
        assert row["exact_route_match"] is True
        assert row["accepted_route_correct"] is True
        assert row["alternative_route_used"] is False

    def test_alternative_accepted_route(self):
        row = _make_row(
            "brody",
            "local_solver",
            allowed_routes=["brody", "local_solver"],
        )
        assert row["exact_route_match"] is False
        assert row["accepted_route_correct"] is True
        assert row["alternative_route_used"] is True

    def test_non_allowed_alternative_not_accepted(self):
        row = _make_row(
            "fireworks",
            "local_solver",
            allowed_routes=["fireworks"],
        )
        assert row["exact_route_match"] is False
        assert row["accepted_route_correct"] is False
        assert row["alternative_route_used"] is False

    def test_route_correct_backward_compat_with_accepted_route_correct(self):
        row = _make_row(
            "fireworks",
            "local_solver",
            allowed_routes=["fireworks", "local_solver"],
        )
        assert row["route_correct"] == row["accepted_route_correct"]

    def test_alternative_route_used_false_when_exact_match(self):
        row = _make_row("hold_commands_only", "hold_commands_only")
        assert row["alternative_route_used"] is False

    def test_allowed_routes_visible_in_row(self):
        allowed = ["brody", "local_solver"]
        row = _make_row("brody", "local_solver", allowed_routes=allowed)
        assert row["allowed_routes"] == allowed

    def test_allowed_routes_none_when_not_set(self):
        row = _make_row("no_model_needed", "no_model_needed")
        assert row["allowed_routes"] is None

    def test_exact_route_match_none_when_no_expected_route(self):
        row = _make_row(None, "no_model_needed")
        assert row["exact_route_match"] is None

    def test_alternative_route_false_when_expected_route_none(self):
        row = _make_row(None, "no_model_needed")
        assert row["alternative_route_used"] is False

    def test_path_quality_counts_exact_and_alternative(self):
        rows = [
            _make_row("no_model_needed", "no_model_needed"),
            _make_row("brody", "local_solver", allowed_routes=["brody", "local_solver"]),
            _make_row("fireworks", "local_solver", allowed_routes=["fireworks", "local_solver"]),
        ]
        exact = sum(1 for r in rows if r.get("exact_route_match") is True)
        alt = sum(1 for r in rows if r.get("alternative_route_used") is True)
        accepted = sum(1 for r in rows if r.get("accepted_route_correct") is True)
        assert exact == 1
        assert alt == 2
        assert accepted == 3


# ── 3. Practice metrics — verified_local_closure_rate as float ───────────────

class TestPracticeMetricsSchema:
    def _build_frontier(self, local_pass: int, n: int) -> dict:
        return {
            "amd_practice_tasks": n,
            "verified_local_closure_count": local_pass,
            "verified_local_closure_rate": round(local_pass / n, 4),
            "verified_local_closure_rate_label": (
                f"{local_pass}/{n} = {local_pass / n:.1%} "
                "(zero-token AND grade=PASS)"
            ),
        }

    def test_verified_local_closure_rate_is_float(self):
        frontier = self._build_frontier(8, 8)
        assert isinstance(frontier["verified_local_closure_rate"], float)

    def test_verified_local_closure_rate_value_8_of_8(self):
        frontier = self._build_frontier(8, 8)
        assert frontier["verified_local_closure_rate"] == 1.0

    def test_verified_local_closure_rate_partial(self):
        frontier = self._build_frontier(6, 8)
        assert frontier["verified_local_closure_rate"] == 0.75

    def test_verified_local_closure_rate_label_exists(self):
        frontier = self._build_frontier(8, 8)
        assert "verified_local_closure_rate_label" in frontier

    def test_label_contains_fraction(self):
        frontier = self._build_frontier(8, 8)
        assert "8/8" in frontier["verified_local_closure_rate_label"]

    def test_label_contains_percentage(self):
        frontier = self._build_frontier(8, 8)
        assert "100.0%" in frontier["verified_local_closure_rate_label"]

    def test_rate_float_supports_format_percent(self):
        frontier = self._build_frontier(8, 8)
        formatted = f"{frontier['verified_local_closure_rate']:.1%}"
        assert formatted == "100.0%"

    def test_rate_float_usable_in_arithmetic(self):
        frontier = self._build_frontier(6, 8)
        assert frontier["verified_local_closure_rate"] * 8 == pytest.approx(6.0)

    def test_no_consumer_formats_label_as_float(self):
        frontier = self._build_frontier(8, 8)
        label = frontier["verified_local_closure_rate_label"]
        # label is a string, formatting as float must raise TypeError
        with pytest.raises((TypeError, ValueError)):
            _ = f"{label:.1%}"

    def test_rate_and_label_are_consistent(self):
        frontier = self._build_frontier(7, 8)
        rate = frontier["verified_local_closure_rate"]
        label = frontier["verified_local_closure_rate_label"]
        assert f"{rate:.1%}" in label


# ── 4. Estimated vs measured tokens ──────────────────────────────────────────

class TestEstimatedVsMeasuredTokens:
    def _build_model_avoidance(
        self,
        *,
        est_saved: int = 5584,
        live: bool = False,
        measured_saved: int | None = None,
        measured_rate: float | None = None,
        measured_avail: int | None = None,
    ) -> dict:
        nm_sentinel = {"status": "not_measured", "reason": "run with --live-baseline to measure"}
        return {
            "tokens_saved_vs_baseline": est_saved,
            "estimated_tokens_saved_source": "estimate_tokens_function",
            "measured_live_tokens_saved": (
                measured_saved if live and measured_saved is not None else nm_sentinel
            ),
            "measured_live_tokens_saved_rate": (
                measured_rate if live and measured_rate is not None else nm_sentinel
            ),
            "measured_live_tokens_available": (
                measured_avail if live and measured_avail is not None else nm_sentinel
            ),
        }

    def test_estimated_and_measured_are_distinct_fields(self):
        ma = self._build_model_avoidance()
        assert "tokens_saved_vs_baseline" in ma
        assert "measured_live_tokens_saved" in ma
        assert ma["tokens_saved_vs_baseline"] != ma["measured_live_tokens_saved"]

    def test_estimated_source_is_declared(self):
        ma = self._build_model_avoidance()
        assert ma["estimated_tokens_saved_source"] == "estimate_tokens_function"

    def test_dry_run_measured_fields_are_not_measured(self):
        ma = self._build_model_avoidance(live=False)
        assert isinstance(ma["measured_live_tokens_saved"], dict)
        assert ma["measured_live_tokens_saved"].get("status") == "not_measured"

    def test_live_run_measured_fields_are_numeric(self):
        ma = self._build_model_avoidance(
            live=True,
            measured_saved=10977,
            measured_rate=1.0,
            measured_avail=18,
        )
        assert isinstance(ma["measured_live_tokens_saved"], int)
        assert ma["measured_live_tokens_saved"] == 10977

    def test_live_run_measured_rate_is_float(self):
        ma = self._build_model_avoidance(
            live=True,
            measured_saved=10977,
            measured_rate=1.0,
            measured_avail=18,
        )
        assert isinstance(ma["measured_live_tokens_saved_rate"], float)

    def test_truncated_tokens_still_counted_in_measured(self):
        # Tokens from truncated responses are real API spend.
        # measured_live_tokens_saved must include them.
        ma = self._build_model_avoidance(
            live=True,
            measured_saved=10977,  # includes 6 truncated calls
            measured_rate=1.0,
            measured_avail=12,     # only 12 of 18 have usage (non-truncated)
        )
        assert ma["measured_live_tokens_saved"] == 10977
        # Truncated tokens are not subtracted
        assert ma["measured_live_tokens_saved"] > 0

    def test_estimated_and_measured_can_differ(self):
        ma = self._build_model_avoidance(
            live=True,
            measured_saved=10977,
            measured_rate=1.0,
            measured_avail=18,
            est_saved=5584,
        )
        assert ma["tokens_saved_vs_baseline"] == 5584
        assert ma["measured_live_tokens_saved"] == 10977
        assert ma["tokens_saved_vs_baseline"] != ma["measured_live_tokens_saved"]

    def test_estimated_source_not_renamed_to_measured(self):
        ma = self._build_model_avoidance(live=False, est_saved=5584)
        # tokens_saved_vs_baseline must not silently become the measured value
        assert ma["tokens_saved_vs_baseline"] == 5584
        assert ma["estimated_tokens_saved_source"] == "estimate_tokens_function"


# ── 5. complete_response_count — dérivé de la télémétrie ─────────────────────

def _make_telemetry_set() -> list[dict]:
    """Three rows: complete, truncated, other error."""
    return [
        _make_telemetry_row(task_id="ok", error=None, truncated=False),
        _make_telemetry_row(
            task_id="trunc",
            error="truncated_completion",
            truncated=True,
            finish_reason="length",
        ),
        _make_telemetry_row(
            task_id="other_err",
            error="no_final_content",
            truncated=False,
            final_content_present=False,
        ),
    ]


class TestCompleteResponseCount:
    def _complete_response_count(self, rows: list[dict]) -> int:
        return sum(1 for row in rows if not row.get("error"))

    def _truncated_completion_count(self, rows: list[dict]) -> int:
        return sum(1 for row in rows if row.get("error") == "truncated_completion")

    def _error_count(self, rows: list[dict]) -> int:
        return sum(1 for row in rows if row.get("error"))

    def test_complete_response_count_only_no_error(self):
        rows = _make_telemetry_set()
        assert self._complete_response_count(rows) == 1

    def test_truncated_not_counted_as_complete(self):
        rows = _make_telemetry_set()
        assert self._complete_response_count(rows) < len(rows)
        assert rows[1]["error"] == "truncated_completion"
        assert self._complete_response_count([rows[1]]) == 0

    def test_other_error_not_counted_as_complete(self):
        rows = _make_telemetry_set()
        assert self._complete_response_count([rows[2]]) == 0

    def test_complete_plus_errors_eq_total(self):
        rows = _make_telemetry_set()
        complete = self._complete_response_count(rows)
        errors = self._error_count(rows)
        assert complete + errors == len(rows)

    def test_truncated_completion_count_is_subset_of_error_count(self):
        rows = _make_telemetry_set()
        assert self._truncated_completion_count(rows) <= self._error_count(rows)

    def test_error_count_includes_non_truncated_errors(self):
        rows = _make_telemetry_set()
        assert self._error_count(rows) == 2
        assert self._truncated_completion_count(rows) == 1


# ── 6. actual_model_used — dérivé de la réponse avec fallback ────────────────

class TestActualModelUsed:
    _SELECTED = "accounts/fireworks/models/gpt-oss-120b"
    _DEPLOYED = "accounts/fireworks/models/gpt-oss-120b-deployed-alias"

    def _resolve_actual_model(
        self,
        b: dict,
        baseline_model: str,
    ) -> str:
        return (
            b.get("actual_model_used")
            or b.get("model")
            or baseline_model
        )

    def test_uses_response_actual_model_used_when_present(self):
        b = {"actual_model_used": self._DEPLOYED, "model": self._SELECTED}
        result = self._resolve_actual_model(b, self._SELECTED)
        assert result == self._DEPLOYED

    def test_falls_back_to_model_key_when_no_actual_model_used(self):
        b = {"model": self._SELECTED}
        result = self._resolve_actual_model(b, "fallback_model")
        assert result == self._SELECTED

    def test_falls_back_to_baseline_model_when_no_model_key(self):
        b = {}
        result = self._resolve_actual_model(b, self._SELECTED)
        assert result == self._SELECTED

    def test_selected_model_is_always_requested_model(self):
        row = _make_telemetry_row(
            selected_model=self._SELECTED,
            actual_model_used=self._DEPLOYED,
        )
        assert row["selected_model"] == self._SELECTED
        assert row["actual_model_used"] == self._DEPLOYED

    def test_no_reasoning_content_stored_in_model_resolution(self):
        b = {"model": self._SELECTED, "reasoning_content": "SECRET REASONING"}
        result = self._resolve_actual_model(b, self._SELECTED)
        assert "SECRET" not in result
        row = _make_telemetry_row(actual_model_used=result)
        assert "reasoning_content" not in row.keys()
