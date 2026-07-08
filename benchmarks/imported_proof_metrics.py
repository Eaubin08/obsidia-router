"""Read-only import of proof benchmark metrics from X108 proof repo.

This module never launches proof runners, never modifies RUN_METRICS_LAST.json,
and never affects Track 1 scoring or routing.

Usage:
    raw = load_proof_metrics(path)  # None → {}
    bloc = build_imported_proof_metrics(raw)
    report["imported_proof_metrics"] = bloc
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Sentinel used when a field is absent in the source file
_NM = "not_measured"

_SOURCE = "imported_from_x108_proofs"


# ── Public API ────────────────────────────────────────────────────────────────


def load_proof_metrics(path: "str | Path | None") -> dict:
    """Read-only JSON loader.

    Returns {} if path is None or empty.
    Raises ValueError with a clear message if path exists but contains invalid JSON.
    Raises FileNotFoundError if an explicit path was given but the file is missing.
    """
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"--proof-metrics-file not found: {p}. "
            "Provide a valid path or omit the flag to skip proof metrics import."
        )
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in proof metrics file {p}: {exc}"
        ) from exc


def build_imported_proof_metrics(raw: "dict | None") -> dict:
    """Build the normalized imported_proof_metrics block for benchmark_report.json.

    - scored_track1 is always False
    - source is always 'imported_from_x108_proofs'
    - missing nested fields become not_measured strings, never raise
    """
    if not raw:
        return _disabled_bloc("no proof metrics file provided")

    pm = raw.get("phase_metrics", {})
    gps = raw.get("gps_semantics", {})
    gps_summary = gps.get("summary", {})
    safety = raw.get("safety_summary", {})

    # ── run_meta ─────────────────────────────────────────────────────────────
    rm = raw.get("run_meta", {})
    run_meta = {
        "proof_status_global": rm.get("status_global", _NM),
        "proof_run_duration_total_s": rm.get("duration_total_s", _NM),
        "proof_commit_sha": rm.get("commit_sha", _NM),
        "proof_runner": rm.get("runner", _NM),
        "proof_profile": rm.get("profile", _NM),
    }

    # ── formal (Lean + TLC) ──────────────────────────────────────────────────
    lb = pm.get("lean_build", {})
    tlc = pm.get("tlc_x108_mc", {})
    tlcd = pm.get("tlc_distributed_x108", {})
    formal = {
        "lean_build_status": lb.get("status", _NM),
        "lean_build_duration_s": lb.get("duration_s", _NM),
        "tlc_x108_status": tlc.get("status", _NM),
        "tlc_x108_duration_s": tlc.get("duration_s", _NM),
        "tlc_x108_states_generated": tlc.get("states_generated", _NM),
        "tlc_x108_distinct_states": tlc.get("distinct_states", _NM),
        "tlc_x108_queue_left": tlc.get("queue_left", _NM),
        "tlc_distributed_status": tlcd.get("status", _NM),
        "tlc_distributed_duration_s": tlcd.get("duration_s", _NM),
        "tlc_distributed_states_generated": tlcd.get("states_generated", _NM),
        "tlc_distributed_distinct_states": tlcd.get("distinct_states", _NM),
        "tlc_distributed_queue_left": tlcd.get("queue_left", _NM),
    }

    # ── verification ─────────────────────────────────────────────────────────
    va = pm.get("verify_all", {})
    vd = pm.get("verify_decision", {})
    verification = {
        "verify_all_status": va.get("status", _NM),
        "verify_all_duration_s": va.get("duration_s", _NM),
        "verify_decision_status": vd.get("status", _NM),
        "verify_decision_duration_s": vd.get("duration_s", _NM),
        "verify_decision_scenarios_checked": vd.get("scenarios_checked", _NM),
    }

    # ── sigma ────────────────────────────────────────────────────────────────
    st = pm.get("sigma_tests", {})
    sp = pm.get("sigma_public", {})
    sigma = {
        "sigma_public_status": sp.get("status", _NM),
        "sigma_public_duration_s": sp.get("duration_s", _NM),
        "sigma_tests_status": st.get("status", _NM),
        "sigma_tests_total": st.get("tests_total", _NM),
        "sigma_tests_passed": st.get("tests_passed", _NM),
        "sigma_tests_failed": st.get("tests_failed", _NM),
        "sigma_slowest_tests": st.get("slowest_tests", _NM),
    }

    # ── GPS semantics ─────────────────────────────────────────────────────────
    gps_block = {
        "gps_cases_total": gps_summary.get("cases_total", _NM),
        "gps_cases_passed": gps_summary.get("cases_passed", _NM),
        "gps_allow_count": gps_summary.get("allow_count", _NM),
        "gps_hold_count": gps_summary.get("hold_count", _NM),
        "gps_block_count": gps_summary.get("block_count", _NM),
        "gps_mean_truth_score": gps_summary.get("mean_truth_score", _NM),
        "gps_mean_sigma_score": gps_summary.get("mean_sigma_score", _NM),
        "gps_mean_mismatch_gap": gps_summary.get("mean_mismatch_gap", _NM),
        "gps_case_summaries": gps.get("cases", []),
    }

    # ── anchor schema ─────────────────────────────────────────────────────────
    qa = pm.get("qa_anchor_schema", {})
    anchor_schema = {
        "anchor_schema_tests_total": qa.get("tests_total", _NM),
        "anchor_schema_tests_passed": qa.get("tests_passed", _NM),
        "qa_anchor_schema_status": qa.get("status", _NM),
    }

    # ── safety summary ────────────────────────────────────────────────────────
    safety_block = dict(safety) if safety else {"status": _NM}

    # ── GPS gate distribution helper ──────────────────────────────────────────
    allow = gps_summary.get("allow_count", 0)
    hold = gps_summary.get("hold_count", 0)
    block = gps_summary.get("block_count", 0)
    total_gps = gps_summary.get("cases_total", 0)
    gps_gate_dist: Any
    if total_gps and isinstance(total_gps, int):
        gps_gate_dist = f"ALLOW={allow} HOLD={hold} BLOCK={block}"
    else:
        gps_gate_dist = _NM

    # ── sigma ratio helper ────────────────────────────────────────────────────
    s_passed = st.get("tests_passed", _NM)
    s_total = st.get("tests_total", _NM)
    sigma_ratio = (
        f"{s_passed}/{s_total}"
        if s_passed != _NM and s_total != _NM
        else _NM
    )

    # ── GPS ratio helper ──────────────────────────────────────────────────────
    g_passed = gps_summary.get("cases_passed", _NM)
    g_total = gps_summary.get("cases_total", _NM)
    gps_ratio = (
        f"{g_passed}/{g_total}"
        if g_passed != _NM and g_total != _NM
        else _NM
    )

    # ── anchor ratio helper ───────────────────────────────────────────────────
    a_passed = qa.get("tests_passed", _NM)
    a_total = qa.get("tests_total", _NM)
    anchor_ratio = (
        f"{a_passed}/{a_total}"
        if a_passed != _NM and a_total != _NM
        else _NM
    )

    safety_status = safety.get("status", _NM) if safety else _NM

    top_proof_metrics = {
        "proof_status_global": run_meta["proof_status_global"],
        "proof_run_duration_total_s": run_meta["proof_run_duration_total_s"],
        "lean_build_status": formal["lean_build_status"],
        "tlc_x108_states_generated": formal["tlc_x108_states_generated"],
        "tlc_x108_distinct_states": formal["tlc_x108_distinct_states"],
        "verify_decision_scenarios_checked": verification["verify_decision_scenarios_checked"],
        "sigma_tests": sigma_ratio,
        "gps_cases": gps_ratio,
        "gps_gate_distribution": gps_gate_dist,
        "gps_mean_mismatch_gap": gps_summary.get("mean_mismatch_gap", _NM),
        "anchor_schema_tests": anchor_ratio,
        "safety_summary_status": safety_status,
    }

    return {
        "enabled": True,
        "source": _SOURCE,
        "scored_track1": False,
        "run_meta": run_meta,
        "formal": formal,
        "verification": verification,
        "sigma": sigma,
        "gps_semantics": gps_block,
        "anchor_schema": anchor_schema,
        "safety_summary": safety_block,
        "top_proof_metrics": top_proof_metrics,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


def not_measured(reason: str, required_input: str = "") -> dict:
    return {
        "status": "not_measured",
        "reason": reason,
        "required_input": required_input,
        "source": _SOURCE,
        "scored_track1": False,
    }


def _disabled_bloc(reason: str) -> dict:
    return {
        "enabled": False,
        "source": _SOURCE,
        "scored_track1": False,
        "status": "not_measured",
        "reason": reason,
        "required_input": "--proof-metrics-file PATH or OBSIDIA_PROOF_METRICS_FILE",
    }


def resolve_proof_metrics_path(
    cli_path: "str | None" = None,
    env_var: str = "OBSIDIA_PROOF_METRICS_FILE",
) -> "str | None":
    """Resolve the proof metrics file path from CLI flag or env var."""
    if cli_path:
        return cli_path
    env_val = os.environ.get(env_var, "").strip()
    return env_val if env_val else None
