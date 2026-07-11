"""Adaptive model triage metrics (LOT E) — pure aggregates over existing
MetricsCollector records. Instrumentation only: this module never decides a
model, never spends a token, and has zero influence on routing, gates, or
the triage policy itself (see app.router.model_triage for that policy).

Doctrine choices (documented once, applied everywhere):

  "code task" canonical source
    = record["intent_type"] == "code_request" — the IR-level signal, always
      present on every record regardless of route. The narrower
      answer_kind == "code_file" (contract-only, computed solely on
      escalation paths) is NOT used here, to keep one honest, universally
      available definition rather than mixing two different signals.

  local-route records carry no triage evidence
    selected_model / selected_rung / selection_reason / ladder_size /
    contract_model_preference / actual_model_used / raw_prompt_chars /
    system_prompt_chars are all None on any record whose route is not
    "fireworks" — no remote selection ever happened, so there is nothing
    truthful to report for that record.

  rung position classes are mutually exclusive (no double counting)
    single_rung   — ladder_size == 1 (first and last coincide; counted once)
    first_rung    — ladder_size > 1 and selected_rung == 0
    last_rung     — ladder_size > 1 and selected_rung == ladder_size - 1
    intermediate  — ladder_size > 1 and 0 < selected_rung < ladder_size - 1
  Every remote-model record falls into exactly one class.

  no cost/token-savings claim is derived from rung position
    higher_rung_calls_avoided is a call COUNT ("calls kept below the
    highest allowed rung"), never converted into tokens or dollars — real
    per-model costs are not measured here.

  rates are fractions in [0.0, 1.0], matching MetricsCollector.summary()'s
  existing convention (e.g. level0_rate); percentage formatting belongs to
  the report renderer, not this module. Division by zero always yields 0.0,
  never an exception.
"""
from __future__ import annotations

_GPT_OSS_120B_MARKER = "gpt-oss-120b"


def _safe_div(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _remote_records(records: list[dict]) -> list[dict]:
    """Records that actually went through the central triage authority —
    i.e. carry a selected_model, not merely route == 'fireworks' (a record
    could in principle be route=='fireworks' from a caller that has not
    been wired through model_triage; selected_model is the stricter, more
    honest filter)."""
    return [r for r in records if r.get("route") == "fireworks"
            and r.get("selected_model")]


def model_call_distribution(records: list[dict]) -> dict[str, int]:
    """{model_name: call_count} over remote records. Names are whatever the
    resolved ladder actually contained — never assumed or hardcoded."""
    dist: dict[str, int] = {}
    for r in _remote_records(records):
        model = r["selected_model"]
        dist[model] = dist.get(model, 0) + 1
    return dist


def model_rung_distribution(records: list[dict]) -> dict[str, int]:
    """{"0": count, "1": count, ...} over remote records with a known rung."""
    dist: dict[str, int] = {}
    for r in _remote_records(records):
        rung = r.get("selected_rung")
        if rung is None:
            continue
        key = str(rung)
        dist[key] = dist.get(key, 0) + 1
    return dist


def rung_position_rates(records: list[dict]) -> dict:
    """Mutually-exclusive rung position classes over remote records with a
    known ladder_size. See module docstring for the single/first/last/
    intermediate doctrine."""
    remote = [r for r in _remote_records(records)
              if r.get("selected_rung") is not None and r.get("ladder_size")]
    total = len(remote)
    single = first = last = intermediate = 0
    for r in remote:
        rung, size = r["selected_rung"], r["ladder_size"]
        if size == 1:
            single += 1
        elif rung == 0:
            first += 1
        elif rung == size - 1:
            last += 1
        else:
            intermediate += 1
    return {
        "rung_position_sample_size": total,
        "single_rung_call_rate": _safe_div(single, total),
        "first_rung_call_rate": _safe_div(first, total),
        "intermediate_rung_call_rate": _safe_div(intermediate, total),
        "last_rung_call_rate": _safe_div(last, total),
    }


def higher_rung_calls_avoided(records: list[dict]) -> dict:
    """Call counts, never a cost claim. See module docstring."""
    remote = [r for r in _remote_records(records)
              if r.get("selected_rung") is not None and r.get("ladder_size")]
    below_highest = sum(1 for r in remote if r["selected_rung"] < r["ladder_size"] - 1)
    at_highest = sum(1 for r in remote if r["selected_rung"] == r["ladder_size"] - 1)
    return {
        "higher_rung_calls_avoided": below_highest,
        "highest_rung_required_calls": at_highest,
    }


def code_task_metrics(records: list[dict]) -> dict:
    """route/intent_type crosstab. Never mixes gate-closed, memory-closed,
    and solver-closed locals under one label — only local_solver counts as
    a genuine local *closure* of a code task."""
    total = len(records)
    local_solver_hits = sum(1 for r in records if r.get("route") == "local_solver")
    code_records = [r for r in records if r.get("intent_type") == "code_request"]
    code_total = len(code_records)
    code_solver_closures = sum(1 for r in code_records if r.get("route") == "local_solver")
    remote_code_calls = sum(1 for r in code_records if r.get("route") == "fireworks")
    return {
        "local_solver_hits": local_solver_hits,
        "local_solver_hit_rate": _safe_div(local_solver_hits, total),
        "code_tasks_total": code_total,
        # code_tasks_closed_locally == code_solver_closures: closure by a
        # deterministic code solver specifically, not any local route.
        "code_tasks_closed_locally": code_solver_closures,
        "code_solver_closures": code_solver_closures,
        "remote_code_calls": remote_code_calls,
        "remote_code_call_rate": _safe_div(remote_code_calls, code_total),
    }


def prompt_size_metrics(records: list[dict]) -> dict:
    """Character counts only — never the prompt content itself."""
    remote = [r for r in _remote_records(records) if r.get("raw_prompt_chars") is not None]
    raw_chars = [r["raw_prompt_chars"] for r in remote]
    system_chars = [r["system_prompt_chars"] for r in remote if r.get("system_prompt_chars") is not None]
    return {
        "total_raw_prompt_chars": sum(raw_chars),
        "average_raw_prompt_chars": round(sum(raw_chars) / len(raw_chars), 1) if raw_chars else 0.0,
        "max_raw_prompt_chars": max(raw_chars) if raw_chars else 0,
        "total_system_prompt_chars": sum(system_chars),
    }


def triage_summary(records: list[dict]) -> dict:
    """Single entry point: merges every LOT E aggregate. Safe on an empty or
    all-local record set — every rate is 0.0, every count is 0, no
    ZeroDivisionError, no fabricated percentage."""
    remote = _remote_records(records)
    dist = model_call_distribution(records)
    out = {
        "model_call_distribution": dist,
        "model_rung_distribution": model_rung_distribution(records),
        "remote_model_calls": len(remote),
        "unique_models_used": len(dist),
        "gpt_oss_120b_call_count": sum(
            n for m, n in dist.items() if _GPT_OSS_120B_MARKER in m
        ),
    }
    out.update(rung_position_rates(records))
    out.update(higher_rung_calls_avoided(records))
    out.update(code_task_metrics(records))
    out.update(prompt_size_metrics(records))
    rungs = [r["selected_rung"] for r in remote if r.get("selected_rung") is not None]
    out["average_selected_rung"] = round(sum(rungs) / len(rungs), 3) if rungs else 0.0
    out["max_selected_rung"] = max(rungs) if rungs else 0
    return out
