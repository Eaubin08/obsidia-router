"""Track 3 replay — verifies a saved ExecutionEnvelope without re-executing any action.

Usage:
    python -m app.track3.replay <receipt.json>
    python -m app.track3.replay --json <receipt.json>

Invariants (never violated by replay):
  - No model calls
  - No external calls
  - No mutations
  - No git / docker operations
  - Receipt file is never overwritten
  - If hash is invalid → REPLAY_MATCH = NO, exit 1
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.ir.unified_ir import build_ir
from app.gates import gates
from app.router.local_solvers import try_local_solvers
from app.track3 import active_plan as active_plan_mod
from app.track3 import capability_resolver
from app.track3 import memory_adapter
from app.track3 import receipt as receipt_mod
from app.track3.t3_solvers import try_t3_solvers


# Fields compared for structural equivalence (timestamps and IDs excluded)
_IR_FIELDS   = ("intent_type", "target_layer", "risk_level", "action_type")
_PLAN_FIELDS = ("intent_type", "risk_level", "world_action_requested",
                "needs_clarification", "selected_execution_mode")


def _solver_to_cap_id(solver: str) -> str:
    if "math" in solver or "rate" in solver or "multiply" in solver:
        return "deterministic_math"
    if "sentiment" in solver:
        return "deterministic_sentiment"
    if "ner" in solver:
        return "deterministic_ner"
    if "fact" in solver:
        return "deterministic_factual"
    if "code" in solver or "cache" in solver or "cap" in solver:
        return "deterministic_code"
    if "summary" in solver or "logic" in solver or "brody" in solver:
        return "deterministic_factual"
    return "structural_answer"


def _gate_to_status(verdict: str) -> str:
    return {
        "HOLD":    "held",
        "DENY":    "denied",
        "CLARIFY": "clarification_required",
    }.get(verdict, "")


def replay(receipt_path: str) -> dict:
    """Load, verify, re-derive, and compare an ExecutionEnvelope receipt.

    Returns a detailed report. Never writes to the receipt file.
    """
    path = Path(receipt_path)
    if not path.exists():
        return {
            "HASH_VALID":    "NO",
            "REPLAY_MATCH":  "NO",
            "error":         f"file not found: {receipt_path}",
            "model_called":  False,
            "external_calls": 0,
        }

    with path.open("r", encoding="utf-8") as fh:
        stored = json.load(fh)

    # ── 1. Schema check ───────────────────────────────────────────────────────
    required = {"schema_version", "run_id", "request", "receipt_hash",
                "decision_authority", "status", "unified_ir", "active_plan",
                "capability_selected", "gate_verdict"}
    missing_fields = required - set(stored)
    if missing_fields:
        return {
            "HASH_VALID":   "NO",
            "REPLAY_MATCH": "NO",
            "error":        f"schema fields missing: {sorted(missing_fields)}",
            "model_called": False,
            "external_calls": 0,
        }

    # ── 2. Hash verification ──────────────────────────────────────────────────
    hash_valid = receipt_mod.verify_hash(stored)
    if not hash_valid:
        return {
            "HASH_VALID":   "NO",
            "REPLAY_MATCH": "NO",
            "error":        "receipt_hash mismatch — envelope may have been tampered",
            "model_called": False,
            "external_calls": 0,
        }

    # ── 3. Re-derive structural fields (deterministic — no model, no network) ─
    raw = stored["request"]
    ir         = build_ir(raw)
    plan       = active_plan_mod.build(raw, ir)
    gate       = gates.evaluate(ir)
    cap_id, _  = capability_resolver.select(plan, gate)

    # On ALLOW paths, re-run deterministic solvers and memory lookup to match
    # what runtime.py actually chose. No model call, no Fireworks, same order as runtime.
    replayed_level = "LEVEL_0"
    if gate["verdict"] == "ALLOW":
        t3 = try_t3_solvers(raw)
        if t3:
            cap_id = _solver_to_cap_id(t3["solver"])
            replayed_level = "LEVEL_1"
        else:
            loc = try_local_solvers(raw)
            if loc:
                cap_id = _solver_to_cap_id(loc["solver"])
                replayed_level = "LEVEL_1"
            else:
                mem = memory_adapter.lookup(raw, ir)
                if mem is not None:
                    cap_id = "memory_lookup"
                    replayed_level = "LEVEL_2"
                else:
                    # LEVEL_3 requires Brody/Qwen — not re-runnable in replay.
                    # Level stays LEVEL_3-or-UNRESOLVED; comparison is lenient below.
                    replayed_level = "LEVEL_3"

    # ── 4. Compare ────────────────────────────────────────────────────────────
    stored_ir   = stored.get("unified_ir",        {})
    stored_plan = stored.get("active_plan",       {})
    stored_gate = stored.get("gate_verdict",      {})
    stored_cap  = stored.get("capability_selected", {})

    ir_diffs = {
        f: (ir[f], stored_ir.get(f))
        for f in _IR_FIELDS
        if ir.get(f) != stored_ir.get(f)
    }
    plan_diffs = {
        f: (plan[f], stored_plan.get(f))
        for f in _PLAN_FIELDS
        if plan.get(f) != stored_plan.get(f)
    }

    gate_match = gate["verdict"] == stored_gate.get("verdict")
    auth_match = stored.get("decision_authority") == "KX108_ONLY"

    # Cap match is lenient on LEVEL_3 paths because Brody/Qwen cannot be re-run.
    # The replayed cap_id at LEVEL_3 is the capability_resolver fallback, not the real one.
    _level3_caps = {"local_qwen", "brody_readonly", "structural_answer"}
    if replayed_level == "LEVEL_3":
        cap_match = stored_cap.get("capability_id") in _level3_caps
    else:
        cap_match = cap_id == stored_cap.get("capability_id")

    # Status is deterministic only on non-ALLOW gate paths
    stored_status   = stored.get("status", "")
    replayed_verdict = gate["verdict"]
    if replayed_verdict in ("HOLD", "DENY", "CLARIFY"):
        expected_status = _gate_to_status(replayed_verdict)
        status_match = stored_status == expected_status
        status_note  = f"deterministic: expected {expected_status!r}"
    else:
        status_match = True   # ALLOW path: status depends on actual execution
        status_note  = "not_verified (ALLOW path — execution-dependent)"

    # Escalation level comparison.
    # LEVEL_3 and UNRESOLVED are both valid stored values when replay infers LEVEL_3
    # (Brody/Qwen cannot be re-run; the original may have succeeded or failed).
    stored_level = stored.get("escalation_level_final", "")
    if replayed_level == "LEVEL_3":
        level_match = stored_level in ("LEVEL_3", "UNRESOLVED")
        level_note  = "lenient: LEVEL_3/UNRESOLVED both accepted (model not re-runnable)"
    else:
        level_match = stored_level == replayed_level
        level_note  = "exact match"

    ir_match   = not ir_diffs
    plan_match = not plan_diffs
    all_match  = all([ir_match, plan_match, gate_match, cap_match,
                      auth_match, status_match, level_match])

    report = {
        "HASH_VALID":             "YES",
        "REPLAY_MATCH":           "YES" if all_match else "NO",
        "ir_match":               ir_match,
        "plan_match":             plan_match,
        "gate_match":             gate_match,
        "cap_match":              cap_match,
        "auth_match":             auth_match,
        "status_match":           status_match,
        "status_note":            status_note,
        "level_match":            level_match,
        "level_note":             level_note,
        "stored_escalation_level":   stored_level,
        "replayed_escalation_level": replayed_level,
        "stored_gate_verdict":    stored_gate.get("verdict"),
        "replayed_gate_verdict":  replayed_verdict,
        "stored_cap_id":          stored_cap.get("capability_id"),
        "replayed_cap_id":        cap_id,
        "ir_diffs":               ir_diffs,
        "plan_diffs":             plan_diffs,
        "model_called":           False,
        "external_calls":         0,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    output_json = False
    paths: list[str] = []
    for arg in args:
        if arg == "--json":
            output_json = True
        else:
            paths.append(arg)

    if not paths:
        print("Usage: python -m app.track3.replay [--json] <receipt.json>",
              file=sys.stderr)
        return 2

    report = replay(paths[0])

    if output_json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        print()
        print("-" * 60)
        print("  OBSIDIA TRACK 3 — REPLAY")
        print("-" * 60)
        for k, v in report.items():
            print(f"  {k:<30}: {v}")
        print("-" * 60)
        print()

    return 0 if report.get("REPLAY_MATCH") == "YES" else 1


if __name__ == "__main__":
    sys.exit(main())
