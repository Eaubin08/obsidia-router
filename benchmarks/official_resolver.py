"""Canonical Track 1 task resolution authority (LOT H).

Lives in benchmarks/ because it depends on the track1 contract modules and
benchmarks/ depends on app/ (never the reverse — LOT C/D layering).

resolve_task() is the ONLY resolution path for official Track 1 answers.
scripts/run_official.py (and therefore the Docker CMD) and
benchmarks/answer_accuracy.py both call this function; neither may keep a
parallel routing/escalation logic.

Pipeline per task:
  1. bounded remote-answer contract built from request signals
  2. run_one(): IR -> gates -> local solvers -> memory -> route decision
  3. escalation gate: brody stub (no BRODY_ENDPOINT) and clarification on a
     hidden task escalate to one bounded Fireworks call
  4. global runtime budget: every remote call timeout is bounded by
     min(ordinary ceiling, remaining budget - output reserve)

Local closure doctrine: local_solver_used alone never proves correctness.
local_candidate_valid is structural (non-empty, non-error deterministic
answer). Semantic validation per category stays in the benchmark graders —
it must never depend on hidden expected answers inside this module.
"""
from __future__ import annotations

import os
import time

from app.adapters import fireworks
from app.cli import run_one
from app.metrics.collector import MetricsCollector
from app.router.decision import DEFAULT_MODEL_LADDER
from app.router.model_triage import select_model_for_request
from benchmarks.track1_remote_answer_contract import build_remote_answer_contract
from benchmarks.track1_escalation_guard import (
    should_escalate_clarification_to_fireworks,
)
from benchmarks.track1_runner import track1_answer

# Official container limit and write/exit reserve (seconds).
OFFICIAL_RUNTIME_BUDGET_S = 600.0
OUTPUT_RESERVE_S = 30.0

_LOCAL_ROUTES = ("local_solver", "memory_hit", "no_model_needed",
                 "hold_commands_only", "denied", "clarification_needed")


class RuntimeContext:
    """Execution context shared by every resolve_task call of one run."""

    def __init__(self,
                 allowed_models: list[str] | None = None,
                 deadline: float | None = None,
                 output_reserve_s: float = OUTPUT_RESERVE_S):
        resolved = allowed_models if allowed_models is not None \
            else fireworks.allowed_models()
        self.model_set_status = ("OFFICIAL_RUNTIME_ALLOWLIST"
                                 if resolved is not None
                                 else "NON_OFFICIAL_FALLBACK_LADDER")
        self.ladder = resolved or list(DEFAULT_MODEL_LADDER)
        self.deadline = deadline
        self.output_reserve_s = output_reserve_s
        self.memory_index: dict = {}
        self.metrics = MetricsCollector()

    def remaining_s(self) -> float | None:
        if self.deadline is None:
            return None
        return self.deadline - time.monotonic()

    def remote_timeout_s(self) -> float | None:
        """Bounded per-call timeout: min(ordinary ceiling, remaining - reserve).

        None means "use the adapter default". Raises TimeoutError when the
        remaining budget cannot fit even a minimal call — the caller must
        produce a controlled error instead of a partial silent file.
        """
        remaining = self.remaining_s()
        if remaining is None:
            return None
        available = remaining - self.output_reserve_s
        if available < fireworks.MIN_TIMEOUT_S:
            raise TimeoutError(
                f"runtime budget exhausted: {remaining:.1f}s remaining, "
                f"{self.output_reserve_s:.0f}s reserved for output")
        return min(fireworks.DEFAULT_TIMEOUT_S, available)


def default_context(allowed_models: list[str] | None = None,
                    with_deadline: bool = False) -> RuntimeContext:
    """Standard context: memory index loaded, optional 600 s deadline."""
    from app.cli import load_memory_index
    ctx = RuntimeContext(
        allowed_models=allowed_models,
        deadline=(time.monotonic() + OFFICIAL_RUNTIME_BUDGET_S
                  if with_deadline else None),
    )
    ctx.memory_index = load_memory_index()
    return ctx


def resolve_task(task: dict, ctx: RuntimeContext) -> dict:
    """Resolve one task through the canonical pipeline.

    task: {"task_id"/"id", "prompt"/"request"} (both schemas accepted).
    Returns the full internal TaskResolution; the official results.json
    projection is {"task_id", "answer"} only (see project_official_row).
    """
    task_id = task.get("task_id") or task.get("id") or "unknown"
    prompt = task.get("prompt") or task.get("request") or ""
    t0 = time.perf_counter()

    contract = build_remote_answer_contract(prompt, allowed_models=ctx.ladder)
    t1_profile = {
        "max_tokens": contract["max_tokens"],
        "system":     contract["contract_prompt"],
        "model":      contract["model_preference"],
        "remote_answer_contract": contract,
    }

    decision = run_one(prompt, ctx.metrics, ctx.memory_index, ctx.ladder,
                       track1_profile=t1_profile)
    route = decision["route"]
    rec = ctx.metrics.records[-1] if ctx.metrics.records else {}

    local_solver_attempted = route in _LOCAL_ROUTES
    local_solver_name = (
        decision.get("solver_name") or rec.get("local_solver")
        or ("local_solver" if route == "local_solver" else None))
    output = decision.get("output") or ""
    local_candidate_valid = (
        route in _LOCAL_ROUTES and bool(output.strip())
        and not output.startswith("[error]")
        and "[dry-run]" not in output)

    # ── Escalation gate (single authority — formerly duplicated in
    #    run_official.py and run_benchmark.py) ─────────────────────────────
    norm_task = {"id": task_id, "request": prompt,
                 **{k: v for k, v in task.items()
                    if k not in ("id", "task_id", "prompt", "request")}}
    needs_escalation = (
        (route == "brody" and not os.environ.get("BRODY_ENDPOINT"))
        or should_escalate_clarification_to_fireworks(
            norm_task, prompt, decision)
    )
    if needs_escalation:
        sel = select_model_for_request(
            prompt, ctx.ladder, answer_kind=contract["answer_kind"])
        model = sel["selected_model"]
        fw = fireworks.chat(
            model, prompt,
            max_tokens=contract["max_tokens"],
            system=contract["contract_prompt"],
            timeout=ctx.remote_timeout_s(),
        )
        decision.update(
            route="fireworks", level=3, model=model,
            actual_model_used=model, output=fw["text"],
            finish_reason=fw.get("finish_reason"),
            final_content_present=fw.get("final_content_present"),
            reasoning_content_present=fw.get("reasoning_content_present"),
            truncated=fw.get("truncated", False),
            remote_response_error=fw.get("error"),
        )
        if ctx.metrics.records:
            last = ctx.metrics.records[-1]
            last["route"] = "fireworks"
            last["dry_run"] = fw.get("dry_run", False)
            last["fireworks_tokens"] = fw.get("total_tokens", 0)
            last["prompt_tokens"] = fw.get("prompt_tokens", 0)
            last["completion_tokens"] = fw.get("completion_tokens", 0)
            last["finish_reason"] = fw.get("finish_reason")
            last["final_content_present"] = fw.get("final_content_present")
            last["reasoning_content_present"] = fw.get(
                "reasoning_content_present")
            last["truncated"] = fw.get("truncated", False)
            last["remote_response_error"] = fw.get("error")
            last["remote_call_avoided"] = False
            last["selected_model"] = model
            last["selected_rung"] = sel["selected_rung"]
            last["selection_reason"] = sel["selection_reason"]
            last["ladder_size"] = len(ctx.ladder)
            last["contract_model_preference"] = contract["model_preference"]
            last["actual_model_used"] = model
            last["raw_prompt_chars"] = len(prompt)
            last["system_prompt_chars"] = len(contract["contract_prompt"])
            last["compression_applied"] = False
        rec = ctx.metrics.records[-1] if ctx.metrics.records else rec
        route = "fireworks"
        local_candidate_valid = False

    latency = round(time.perf_counter() - t0, 4)
    remote = (route == "fireworks") and not rec.get("dry_run", False)

    answer_row = {
        "id": task_id, "request": prompt,
        "actual_route": route,
        "intent_type": decision["ir"]["intent_type"],
        "missing": decision["ir"].get("missing", []),
        "gate_matched": decision["gate"].get("matched"),
        "output": decision.get("output", ""),
        "memory_entry": decision.get("memory_entry"),
        "topic_name": decision.get("topic", {}).get("topic", "general"),
    }
    answer = track1_answer(answer_row)

    return {
        "task_id": task_id,
        "answer": answer,
        "category": contract["answer_kind"],
        "route": route,
        "level": decision["level"],
        "gate_verdict": decision["gate"]["verdict"],
        "gate_matched": decision["gate"].get("matched"),
        "intent_type": decision["ir"]["intent_type"],
        "target_layer": decision["ir"]["target_layer"],
        "local_solver_attempted": local_solver_attempted,
        "local_solver_name": local_solver_name,
        "local_candidate_valid": local_candidate_valid,
        "local_validation_reason": (
            "structural: deterministic non-empty local answer"
            if local_candidate_valid else
            ("remote route" if route == "fireworks" else "empty_or_error")),
        "remote_required": route == "fireworks",
        "selected_model": rec.get("actual_model_used") if remote else None,
        "remote_calls": 1 if remote else 0,
        "prompt_tokens": rec.get("prompt_tokens", 0),
        "completion_tokens": rec.get("completion_tokens", 0),
        "total_tokens": rec.get("fireworks_tokens", 0),
        "latency_s": latency,
        "finish_reason": rec.get("finish_reason"),
        "truncated": rec.get("truncated", False),
        "error": rec.get("remote_response_error"),
        # audit-only triage fields (never in results.json)
        "selected_rung": rec.get("selected_rung"),
        "selection_reason": rec.get("selection_reason"),
        "ladder_size": rec.get("ladder_size"),
        "contract_model_preference": rec.get("contract_model_preference"),
        "raw_prompt_chars": len(prompt),
        "remote_call_avoided": rec.get("remote_call_avoided", True),
    }


def project_official_row(resolution: dict) -> dict:
    """Strict AMD schema projection — the ONLY fields ever written to
    /output/results.json."""
    return {"task_id": resolution["task_id"], "answer": resolution["answer"]}
