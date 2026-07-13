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
from benchmarks.track1_remote_answer_contract import (
    build_remote_answer_contract,
    build_compact_override,
)
from benchmarks.track1_prompt_compressor import build_frontier_remote_prompt
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
        # Tracks tasks remaining for per-task budget calculation.
        # Updated by the runner before each resolve_task call.
        self.tasks_remaining: int = 1

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

    # QWEN_ZERO: patch fireworks.chat to a no-op BEFORE run_one() so no
    # socket connection is attempted even when FIREWORKS_API_KEY is set.
    # Module-attribute patch works because cli.py holds a reference to the
    # fireworks module object (not a local copy of .chat).
    _qwen_zero_mode = os.environ.get("TRACK1_QWEN_ZERO", "").strip() == "1"
    _original_fw_chat = None
    if _qwen_zero_mode:
        import app.adapters.fireworks as _fw_mod
        _original_fw_chat = _fw_mod.chat
        def _qwen_zero_fw_blocker(model, prompt_text, **kwargs):  # noqa: E306
            return {
                "dry_run": True, "model": model,
                "text": "[qwen_zero] fireworks.chat blocked",
                "prompt_tokens": 0, "completion_tokens": 0,
                "total_tokens": 0, "latency_s": 0.0,
            }
        _fw_mod.chat = _qwen_zero_fw_blocker
    try:
        decision = run_one(prompt, ctx.metrics, ctx.memory_index, ctx.ladder,
                           track1_profile=t1_profile)
    finally:
        if _qwen_zero_mode and _original_fw_chat is not None:
            import app.adapters.fireworks as _fw_mod
            _fw_mod.chat = _original_fw_chat
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
    # LOTS M0/M1/M5: for genuine local_solver closures, the semantic bridge
    # must also confirm the candidate (English, non-empty) and emits an
    # audit-only certificate + signature into the internal metrics record.
    # Governed routes (HOLD/DENY/CLARIFY/no_model) are NOT re-validated:
    # a governed verdict is a correct outcome, not a candidate answer.
    if local_candidate_valid and route == "local_solver":
        from app.semantic.runtime_bridge import validate_local_closure
        bridge = validate_local_closure(local_solver_name, prompt, output)
        if ctx.metrics.records:
            rec_last = ctx.metrics.records[-1]
            rec_last["semantic_signature"] = bridge["semantic_signature"]
            rec_last["closure_certificate"] = bridge["certificate"]
        if not bridge["closure_safe"]:
            local_candidate_valid = False

    # ── Adaptive Local Capability Loop ───────────────────────────────────────
    # Runs AFTER the initial solver cascade (run_one) but BEFORE Fireworks
    # escalation. Provides additional strategy passes (decomposition, alternate
    # normalisation) with time-based termination. Mode: SAFE (default) or ZERO.
    from app.router.local_loop import run_local_loop, get_local_mode, LocalMode
    _local_mode = get_local_mode()
    _loop_result = None
    # Only run the loop when the initial pass did NOT already close locally.
    governed_routes = {"hold_commands_only", "denied", "clarification_needed"}
    if not local_candidate_valid and route not in governed_routes:
        # Capture original state BEFORE any loop upgrade so we can safely revert.
        _pre_loop_route = route
        _pre_loop_output = decision.get("output", "")
        _loop_result = run_local_loop(
            prompt,
            mode=_local_mode,
            global_deadline=(
                time.monotonic() + ctx.remaining_s()
                if ctx.remaining_s() is not None else None),
            remaining_tasks=ctx.tasks_remaining,
        )
        if _loop_result.final_status == "VALID" and _loop_result.final_candidate:
            # Upgrade the decision to local_solver with the loop's candidate
            decision.update(
                route="local_solver",
                output=_loop_result.final_candidate,
                reason=f"local_loop:{_loop_result.termination_reason}",
            )
            route = "local_solver"
            local_solver_name = _loop_result.strategies_attempted[-1] if _loop_result.strategies_attempted else "local_loop"
            local_candidate_valid = True
            local_solver_attempted = True
            # Re-run semantic bridge validation on the loop's candidate
            from app.semantic.runtime_bridge import validate_local_closure
            bridge2 = validate_local_closure(local_solver_name, prompt, _loop_result.final_candidate)
            if ctx.metrics.records:
                rec_last2 = ctx.metrics.records[-1]
                rec_last2["semantic_signature"] = bridge2["semantic_signature"]
                rec_last2["closure_certificate"] = bridge2["certificate"]
            if not bridge2["closure_safe"]:
                # Restore to the actual pre-loop route and output, not the
                # just-set "local_solver" — reading decision.get("route") here
                # would return the value we just wrote, not the original.
                local_candidate_valid = False
                route = _pre_loop_route
                decision["route"] = _pre_loop_route
                decision["output"] = _pre_loop_output

    # Telemetry for the loop (audit-only, never in results.json)
    if ctx.metrics.records and _loop_result is not None:
        last_rec = ctx.metrics.records[-1]
        last_rec["local_loop_enabled"] = True
        last_rec["local_loop_mode"] = _loop_result.mode
        last_rec["local_loop_strategies"] = _loop_result.strategies_attempted
        last_rec["local_loop_passes"] = len(_loop_result.strategies_attempted)
        last_rec["local_loop_candidates"] = _loop_result.candidates_generated
        last_rec["local_loop_elapsed_ms"] = _loop_result.local_elapsed_ms
        last_rec["local_loop_termination"] = _loop_result.termination_reason
        last_rec["local_loop_valid"] = _loop_result.final_status == "VALID"
        last_rec["local_loop_soft_budget_s"] = _loop_result.task_soft_budget_s
        last_rec["local_loop_budget_s"] = _loop_result.local_budget_s
        last_rec["local_loop_reserve_s"] = _loop_result.remote_reserve_s

    # ── Escalation gate (single authority — formerly duplicated in
    #    run_official.py and run_benchmark.py) ─────────────────────────────
    norm_task = {"id": task_id, "request": prompt,
                 **{k: v for k, v in task.items()
                    if k not in ("id", "task_id", "prompt", "request")}}
    # Core score-recovery rule: an answerable task (route already passed
    # gates as local_solver — i.e. ALLOW, not governed) whose local candidate
    # turned out absent/invalid must fall back to Fireworks. A rejected or
    # missing local candidate must never silently become the final answer.
    local_candidate_missing_or_invalid = (
        route == "local_solver" and not local_candidate_valid)
    # In ZERO_TOKEN mode, never escalate to Fireworks regardless of route.
    _zero_mode = (_local_mode == LocalMode.ZERO)
    needs_escalation = (
        not _zero_mode
        and (
            (route == "brody" and not os.environ.get("BRODY_ENDPOINT"))
            or local_candidate_missing_or_invalid
            or should_escalate_clarification_to_fireworks(
                norm_task, prompt, decision)
        )
    )
    if needs_escalation:
        sel = select_model_for_request(
            prompt, ctx.ladder, answer_kind=contract["answer_kind"])
        model = sel["selected_model"]
        compact = build_compact_override(prompt, contract["answer_kind"])
        remote_prompt, prompt_meta = build_frontier_remote_prompt(
            prompt, contract["answer_kind"]
        )
        # Bounded adaptive budget: only MULTI_PART_DIRECT prompts get a
        # higher completion budget (ceiling 320), so a reasoning model does
        # not exhaust its visible-answer budget before covering every
        # sub-question. comparison/structured_summary/code_file untouched.
        from app.semantic.remote_complexity import (
            classify_remote_complexity, adaptive_completion_budget)
        complexity_profile = classify_remote_complexity(prompt, contract["answer_kind"])
        completion_budget, budget_reason = adaptive_completion_budget(
            compact["completion_budget"], complexity_profile)

        from app.semantic.remote_failure import classify_remote_failure, is_retryable
        fw = fireworks.chat(
            model, remote_prompt,
            max_tokens=completion_budget,
            system=compact["compact_system"],
            timeout=ctx.remote_timeout_s(),
        )
        attempt1_reason = classify_remote_failure(fw)
        retry_attempted = False
        retry_reason = None
        if is_retryable(attempt1_reason):
            # Single bounded retry: same model (ALLOWED_MODELS/ladder is
            # not re-queried — no new model invented), budget capped at
            # the direct-answer ceiling, only if enough runtime remains.
            _budget_allows_retry = True
            retry_timeout = None
            try:
                retry_timeout = ctx.remote_timeout_s()
            except TimeoutError:
                _budget_allows_retry = False
            if _budget_allows_retry and (retry_timeout is None or retry_timeout >= 3.0):
                retry_attempted = True
                retry_budget = min(max(completion_budget, 256), 320)
                fw2 = fireworks.chat(
                    model, remote_prompt,
                    max_tokens=retry_budget,
                    system=compact["compact_system"] + " Provide the final answer only.",
                    timeout=retry_timeout,
                )
                retry_reason = classify_remote_failure(fw2)
                fw1 = fw
                fw = fw2  # the retry result becomes the projected attempt
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
            last["system_prompt_chars"] = len(compact["compact_system"])
            last["compression_applied"] = True
            last["compact_profile"] = compact["compact_profile"]
            last["estimated_prompt_tokens"] = compact["estimated_prompt_tokens"]
            last["completion_budget"] = compact["completion_budget"]
            last["over_300"] = fw.get("total_tokens", 0) > 300
            last["prompt_chars_before"] = prompt_meta["prompt_chars_before"]
            last["prompt_chars_after"] = prompt_meta["prompt_chars_after"]
            last["prompt_compression_applied"] = prompt_meta["prompt_compression_applied"]
            last["compression_ratio"] = prompt_meta["compression_ratio"]
            last["citer_used"] = prompt_meta["citer_used"]
            # Retry telemetry: both attempts always accounted for, never
            # hidden. attempt_1_* fields are only present when a retry
            # actually happened (retry_attempted=True).
            last["remote_complexity_profile"] = complexity_profile.value
            last["budget_reason"] = budget_reason
            last["remote_attempt_count"] = 2 if retry_attempted else 1
            last["retry_attempted"] = retry_attempted
            if retry_attempted:
                last["attempt_1_model"] = model
                last["attempt_1_tokens"] = fw1.get("total_tokens", 0)
                last["attempt_1_finish_reason"] = fw1.get("finish_reason")
                last["attempt_1_failure_reason"] = attempt1_reason.value
                last["attempt_2_model"] = model
                last["attempt_2_tokens"] = fw.get("total_tokens", 0)
                last["attempt_2_finish_reason"] = fw.get("finish_reason")
                last["attempt_2_result"] = retry_reason.value if retry_reason else None
                last["total_remote_tokens"] = (
                    fw1.get("total_tokens", 0) + fw.get("total_tokens", 0))
                last["total_remote_latency"] = round(
                    fw1.get("latency_s", 0.0) + fw.get("latency_s", 0.0), 3)
            else:
                last["total_remote_tokens"] = fw.get("total_tokens", 0)
                last["total_remote_latency"] = fw.get("latency_s", 0.0)
            # The official token score must count BOTH attempts when a
            # retry happened — never just the second call's cost.
            last["fireworks_tokens"] = last["total_remote_tokens"]
        rec = ctx.metrics.records[-1] if ctx.metrics.records else rec
        route = "fireworks"
        local_candidate_valid = False

    # ── Qwen Zero local inference (TRACK1_QWEN_ZERO=1) ───────────────────────
    # Runs ONLY when: QWEN_ZERO active, no valid local candidate, not governed.
    # Uses the existing validate/repair pipeline from the Fireworks path.
    # UNRESOLVED on any Qwen failure (no second attempt, no Fireworks fallback).
    _qwen_zero_tokens = 0
    _qwen_zero_elapsed_ms = 0.0
    _qwen_zero_valid = False
    _qwen_zero_error: str | None = None
    _qwen_zero_repair_applied = False
    _qwen_zero_repair_ops: list[str] = []
    if _qwen_zero_mode and not local_candidate_valid and route not in governed_routes:
        from app.adapters import qwen_local as _qwen_mod
        from app.semantic.remote_validation import validate_remote_output
        from app.semantic.remote_repair import repair_remote_output
        from benchmarks.output_constraints import parse_output_constraints
        _qr = _qwen_mod.chat(prompt, answer_kind=contract.get("answer_kind", ""))
        _qwen_zero_elapsed_ms = _qr.get("elapsed_ms", 0.0)
        _qwen_zero_tokens = _qr.get("local_model_tokens") or 0
        if _qr["success"] and _qr["text"]:
            _oc = parse_output_constraints(prompt)
            _code_only = contract["answer_kind"] == "code_file" or _oc.code_only
            _qwen_text = _qr["text"]
            _qvalid, _qreasons = validate_remote_output(
                _qwen_text, code_only=_code_only,
                allowed_labels=_oc.allowed_labels,
                sentence_count=_oc.sentence_count,
            )
            if not _qvalid:
                _qrep = repair_remote_output(
                    _qwen_text, code_only=_code_only,
                    allowed_labels=_oc.allowed_labels,
                    sentence_count=_oc.sentence_count,
                )
                if _qrep.repair_applied:
                    _qrevalid, _ = validate_remote_output(
                        _qrep.repaired, code_only=_code_only,
                        allowed_labels=_oc.allowed_labels,
                        sentence_count=_oc.sentence_count,
                    )
                    if _qrevalid:
                        _qwen_text = _qrep.repaired
                        _qvalid = True
                        _qwen_zero_repair_applied = True
                        _qwen_zero_repair_ops = _qrep.repair_operations
            if _qvalid:
                _qwen_zero_valid = True
                decision.update(route="local_solver", output=_qwen_text)
                route = "local_solver"
                local_candidate_valid = True
                local_solver_attempted = True
                local_solver_name = "qwen_local"
        else:
            _qwen_zero_error = _qr.get("error", "qwen not available")
        # Audit telemetry — never in project_official_row()
        if ctx.metrics.records:
            _qlast = ctx.metrics.records[-1]
            _qlast["qwen_zero_attempted"] = True
            _qlast["qwen_zero_valid"] = _qwen_zero_valid
            _qlast["qwen_zero_tokens"] = _qwen_zero_tokens
            _qlast["qwen_zero_elapsed_ms"] = _qwen_zero_elapsed_ms
            _qlast["qwen_zero_error"] = _qwen_zero_error
            _qlast["qwen_zero_repair_applied"] = _qwen_zero_repair_applied
            _qlast["qwen_zero_repair_ops"] = _qwen_zero_repair_ops

    latency = round(time.perf_counter() - t0, 4)
    remote = (route == "fireworks") and not rec.get("dry_run", False)

    # ── Independent TaskKind classification (never derived from the route
    #    or the gate verdict — this is what makes GOVERNED_BUT_ANSWERABLE
    #    detectable instead of tautologically always zero) ─────────────────
    from app.semantic.task_kind import classify_task_kind, TaskKind
    task_kind = classify_task_kind(prompt)

    # ── Explicit internal resolution status — single canonical authority
    #    (app.semantic.resolution_status.ResolutionStatus); audit-only,
    #    never leaked into the official {"task_id","answer"} projection ────
    from app.semantic.resolution_status import ResolutionStatus, SAFE_TO_PROJECT
    solver_exceptions = decision.get("local_solver_exceptions", [])
    remote_valid = None
    remote_rejection_reason = None
    repair_applied = False
    repair_operations: list[str] = []
    governed_routes = {"hold_commands_only", "denied", "clarification_needed"}
    if route in governed_routes:
        status = ResolutionStatus.GOVERNED_WORLD_ACTION
    elif route == "fireworks":
        if remote:
            from app.semantic.remote_validation import validate_remote_output
            from app.semantic.remote_repair import repair_remote_output
            from benchmarks.output_constraints import parse_output_constraints
            # Single authority for output constraints: derived from the
            # prompt itself, never duplicated between validator and repair.
            oc = parse_output_constraints(prompt)
            raw_output = decision.get("output", "")
            code_only = contract["answer_kind"] == "code_file" or oc.code_only
            remote_valid, remote_reasons = validate_remote_output(
                raw_output, code_only=code_only,
                allowed_labels=oc.allowed_labels,
                sentence_count=oc.sentence_count,
            )
            if not remote_valid:
                # Bounded, deterministic repair attempt (no second model
                # call): mechanical fixes only, then re-validate once.
                rep = repair_remote_output(
                    raw_output, code_only=code_only,
                    allowed_labels=oc.allowed_labels,
                    sentence_count=oc.sentence_count,
                )
                if rep.repair_applied:
                    revalid, revalid_reasons = validate_remote_output(
                        rep.repaired, code_only=code_only,
                        allowed_labels=oc.allowed_labels,
                        sentence_count=oc.sentence_count,
                    )
                    repair_applied = True
                    repair_operations = rep.repair_operations
                    if revalid:
                        decision["output"] = rep.repaired
                        remote_valid = True
                        remote_reasons = []
                        status = ResolutionStatus.REMOTE_REPAIRED
                    else:
                        remote_valid = False
                        remote_reasons = revalid_reasons
                        status = ResolutionStatus.REMOTE_INVALID
                else:
                    status = ResolutionStatus.REMOTE_INVALID
            else:
                status = ResolutionStatus.REMOTE_VALID
            remote_rejection_reason = None if remote_valid else ",".join(remote_reasons)
        else:
            status = ResolutionStatus.REMOTE_ATTEMPTED  # dry-run: no key present
    elif local_candidate_valid:
        status = ResolutionStatus.LOCAL_VALID
    elif not local_solver_attempted and solver_exceptions:
        # No candidate reached, but at least one solver raised along the
        # way: this is a recoverable-error abstention, not a plain "no
        # solver matched" — distinct telemetry, same REMOTE_REQUIRED fate.
        status = ResolutionStatus.LOCAL_EXCEPTION
    elif not local_solver_attempted:
        status = ResolutionStatus.LOCAL_UNAVAILABLE
    else:
        status = ResolutionStatus.LOCAL_INVALID
    resolution_status = status.value

    # Non-circular cross-check: an ANSWER_TASK that ended up governed is a
    # gate-classification bug, detectable only because task_kind is computed
    # independently of route/gate/resolution_status.
    governed_but_answerable = (
        task_kind == TaskKind.ANSWER_TASK
        and status == ResolutionStatus.GOVERNED_WORLD_ACTION)

    # SAFE_TO_PROJECT is enforced as a real value-level gate, not just a
    # string-absence check: for an ANSWER_TASK, a status outside this set
    # must never be represented as a successful resolution.
    safe_to_project = status in SAFE_TO_PROJECT

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
        "remote_attempted": route == "fireworks",
        "remote_valid": remote_valid,
        "remote_rejection_reason": remote_rejection_reason,
        "remote_repair_applied": repair_applied,
        "remote_repair_operations": repair_operations,
        "final_resolution_status": resolution_status,
        "final_answer_present": bool(answer.strip()),
        # Independent classification (app.semantic.task_kind), NOT derived
        # from route/gate — this is what makes governed_but_answerable a
        # real, failable cross-check instead of a tautology.
        "task_kind": task_kind.value,
        "answerable": task_kind == TaskKind.ANSWER_TASK,
        "world_action": task_kind == TaskKind.WORLD_ACTION,
        "governed_but_answerable": governed_but_answerable,
        "safe_to_project": safe_to_project,
        "local_solver_exceptions": solver_exceptions,
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
        # Qwen Zero audit fields (0 / None / False when not in QWEN_ZERO mode)
        "qwen_zero_attempted": _qwen_zero_mode and route not in governed_routes,
        "qwen_zero_valid": _qwen_zero_valid,
        "qwen_zero_tokens": _qwen_zero_tokens,
        "qwen_zero_elapsed_ms": _qwen_zero_elapsed_ms,
        "qwen_zero_error": _qwen_zero_error,
        "qwen_zero_repair_applied": _qwen_zero_repair_applied,
    }


def project_official_row(resolution: dict) -> dict:
    """Strict AMD schema projection — the ONLY fields ever written to
    /output/results.json."""
    return {"task_id": resolution["task_id"], "answer": resolution["answer"]}
