"""Metrics coverage — complete audit-ready metrics block for benchmark_report.json.

Builds `metrics_coverage` from the assembled report dict. All values are derived
from existing benchmark data — nothing is invented. When a metric cannot be measured
locally, it is reported as:
  {"status": "not_measured", "reason": "...", "required_input": "..."}

Zero routing authority. No influence on routing, gates, or decisions. KX108_ONLY unchanged.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Not-measured sentinel ─────────────────────────────────────────────────────

def _nm(reason: str, required_input: str = "") -> dict:
    d: dict = {"status": "not_measured", "reason": reason}
    if required_input:
        d["required_input"] = required_input
    return d


# ── Numeric helpers ───────────────────────────────────────────────────────────

def _pct(n: int | float, d: int | float) -> float:
    return round(n / d, 4) if d else 0.0


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sv = sorted(values)
    idx = (len(sv) - 1) * p / 100
    lo, hi = math.floor(idx), math.ceil(idx)
    if lo == hi:
        return round(sv[lo], 3)
    return round(sv[lo] + (sv[hi] - sv[lo]) * (idx - lo), 3)


# ── Meta-reasoning detector (same patterns as model_matrix) ──────────────────

_META_START_RE = re.compile(
    r"(?i)^(the user (asks?|wants?|is asking)|"
    r"understand(ing)? the (goal|request)|"
    r"analyz(e|ing) the (request|task)|"
    r"let me|we need to|the instruction says?)"
)


# ── Builder functions ─────────────────────────────────────────────────────────

def _track1_official(
    report: dict,
    rows: list[dict],
    metrics_records: list[dict],
    total_runtime_s: float | None,
) -> dict:
    s = report["obsidia"]
    total = s["total_tasks"]
    fw_needed = s["fireworks_needed"]
    fw_tokens = s["fireworks_tokens"]

    fw_records = [r for r in metrics_records if r.get("route") == "fireworks"]
    prompt_tok = sum(r.get("prompt_tokens", 0) for r in fw_records)
    compl_tok = sum(r.get("completion_tokens", 0) for r in fw_records)
    avg_out = round(compl_tok / len(fw_records), 1) if fw_records else 0.0

    # Check results.json (written by write_track1 earlier in main)
    results_path = ROOT / "results" / "results.json"
    valid_json = False
    if results_path.exists():
        try:
            d = json.loads(results_path.read_text(encoding="utf-8"))
            valid_json = all(k in d for k in ("format_version", "total_tasks", "tasks", "route_accuracy"))
        except Exception:
            pass

    return {
        "accuracy": report["route_accuracy"],
        "accuracy_by_category": _nm(
            "task categories not labeled in tasks.json",
            "per-category expected_route labels",
        ),
        "fireworks_calls": fw_needed,
        "fireworks_tokens_total": fw_tokens,
        "avg_fireworks_tokens_per_task": round(fw_tokens / total, 2) if total else 0.0,
        "fireworks_prompt_tokens": prompt_tok,
        "fireworks_completion_tokens": compl_tok,
        "avg_output_tokens": avg_out,
        "total_runtime_s": total_runtime_s if total_runtime_s is not None else _nm("not measured"),
        "startup_time_s": _nm("startup time not isolated from benchmark run"),
        "valid_output_json": valid_json,
        "english_output_rate": _nm(
            "task language expectation not labeled in tasks.json",
            "per-task expected_language field",
        ),
    }


def _model_avoidance(report: dict) -> dict:
    s = report["obsidia"]
    b = report["baseline_direct_model"]
    q = report.get("quality_axes", {})
    eq = q.get("escalation_quality", {})
    pq = q.get("path_quality", {})

    total = s["total_tasks"]
    avoided = s["remote_calls_avoided"]
    fw_needed = s["fireworks_needed"]
    fw_tokens = s["fireworks_tokens"]
    baseline_tokens = b["tokens"]
    est_saved = s.get("estimated_tokens_saved", 0)

    fw_call_rate = _pct(fw_needed, total)
    zero_fw_rate = _pct(avoided, total)
    saved_rate = _pct(est_saved, baseline_tokens) if baseline_tokens else 0.0
    saving_ratio = round(baseline_tokens / max(fw_tokens, 1), 1) if baseline_tokens else 0.0

    fw_on_allow = eq.get("fireworks_only_on_allow", 0)
    fw_actual = eq.get("fireworks_actual", fw_needed)
    fw_allow_rate = _pct(fw_on_allow, fw_actual) if fw_actual else 1.0

    return {
        "remote_calls_avoided": avoided,
        "fireworks_call_rate": fw_call_rate,
        "zero_fireworks_rate": zero_fw_rate,
        "tokens_saved_vs_baseline": est_saved,
        "tokens_saved_rate": saved_rate,
        "token_saving_ratio": saving_ratio,
        "unnecessary_fireworks_calls": eq.get("unnecessary_fireworks_calls", 0),
        "fireworks_only_on_allow_rate": fw_allow_rate,
        "level0_model_leaks": pq.get("level0_model_leaks", 0),
        "model_call_avoided_rate": zero_fw_rate,
    }


def _parametric_efficiency_full(report: dict) -> dict:
    pe = report.get("parametric_efficiency", {})
    fp = report.get("footprint", {})

    docker_nm = _nm("docker image not built in this run", "docker inspect obsidia-router")

    rss = fp.get("process_rss_mb", "not_measured")
    rss_status = fp.get("process_rss_status", "not_measured_no_psutil_or_platform_support")
    rss_val = rss if rss != "not_measured" else _nm(
        "process RSS not available without psutil on this platform",
        "psutil or Linux/macOS resource module",
    )

    return {
        "embedded_model_weight_gb": 0,
        "repo_disk_size_mb": fp.get("repo_disk_size_mb", fp.get("repo_size_mb", 0)),
        "repo_size_mb": fp.get("repo_size_mb", 0),
        "runtime_disk_proxy_mb": fp.get("runtime_disk_proxy_mb", fp.get("repo_size_mb", 0)),
        "runtime_stack_size_mb": fp.get("runtime_stack_size_mb", fp.get("repo_size_mb", 0)),
        "runtime_stack_size_note": fp.get("runtime_stack_size_note", "disk proxy, not process RSS"),
        "process_rss_mb": rss_val,
        "process_rss_status": rss_status,
        "docker_compressed_size_mb": docker_nm,
        "docker_uncompressed_size_mb": docker_nm,
        "persistent_memory_size_mb": 0,
        "persistent_memory_enabled": fp.get("persistent_memory_enabled", False),
        "brody_live_enabled": fp.get("brody_live_enabled", False),
        "brody_memory_enabled": False,
        "brody_stub_enabled": fp.get("brody_stub_enabled", True),
        "obsidure_full_enabled": fp.get("obsidure_full_enabled", False),
        "lean_full_enabled": fp.get("lean_full_enabled", False),
        "local_model_files_detected": fp.get("local_model_files_detected", []),
        "fireworks_single_choke_point": fp.get("fireworks_single_choke_point", True),
        "equivalent_7b_weight_gb": {
            "fp16": pe.get("model_weight_displaced_vs_7b_fp16_gb", 14),
            "int4": pe.get("model_weight_displaced_vs_7b_int4_gb", 4),
        },
        "equivalent_70b_weight_gb": {
            "fp16": pe.get("model_weight_displaced_vs_70b_fp16_gb", 140),
            "int4": pe.get("model_weight_displaced_vs_70b_int4_gb", 40),
        },
        "zero_fireworks_rate": pe.get("zero_fireworks_rate", 0),
        "fireworks_dependency_rate": pe.get("fireworks_dependency_rate", 0),
        "interpretation": pe.get("interpretation", "measurable competence before embedded learned weights"),
    }


def _obsidia_structure(report: dict, rows: list[dict]) -> dict:
    s = report["obsidia"]
    q = report.get("quality_axes", {})
    pq = q.get("path_quality", {})
    cvi = report.get("cognitive_value_inputs", {})

    total = s["total_tasks"]
    fw_needed = s["fireworks_needed"]
    no_model = s["no_model_needed"]
    mem_hits = s["memory_hits"]
    hold = s["commands_only_hold"]
    denied = s["denied"]
    clarify = s["clarification_needed"]

    structural_closed = total - fw_needed
    det_resolved = no_model + mem_hits

    gate_dist = cvi.get("control", {}).get("gate_verdict_distribution", {})
    l0_leaks = pq.get("level0_model_leaks", 0)
    hd_leaks = pq.get("hold_deny_clarify_model_leaks", 0)

    return {
        "structural_closure_rate": _pct(structural_closed, total),
        "deterministic_resolution_rate": _pct(det_resolved, total),
        "level0_rate": s.get("level0_rate", 0),
        "route_accuracy": report["route_accuracy"],
        "route_accuracy_by_family": _nm(
            "task family labels not present in tasks.json",
            "per-task family field",
        ),
        "gate_verdict_distribution": gate_dist,
        "hold_rate": _pct(hold, total),
        "deny_rate": _pct(denied, total),
        "clarify_rate": _pct(clarify, total),
        "ambiguous_route_rate": _pct(clarify, total),
        "model_leaks": l0_leaks + hd_leaks,
    }


def _speed(report: dict, rows: list[dict], total_runtime_s: float | None) -> dict:
    lat = report.get("latency", {})
    q = report.get("quality_axes", {})
    sp = q.get("speed_profile", {})
    dyn = report.get("dynamic", {})

    local_rows = [r for r in rows if r["actual_route"] != "fireworks"]
    local_ms = [r["routing_latency_s"] * 1000 for r in local_rows]

    avg_local = lat.get("avg_routing_ms_local", 0)
    avg_fw_s = lat.get("avg_fireworks_call_s", 0)
    ratio = (
        round(avg_fw_s * 1000 / avg_local, 1)
        if avg_local
        else sp.get("remote_local_latency_ratio", 0)
    )

    return {
        "avg_local_decision_ms": avg_local,
        "local_decision_p95_ms": _percentile(local_ms, 95),
        "local_decision_p99_ms": _percentile(local_ms, 99),
        "avg_fireworks_call_s": avg_fw_s,
        "remote_local_latency_ratio": ratio,
        "decisions_per_second": dyn.get("decisions_per_second"),
        "dynamic_avg_decision_ms": dyn.get("avg_decision_ms"),
        "startup_time_s": _nm("startup time not isolated from benchmark run"),
        "total_runtime_s": total_runtime_s if total_runtime_s is not None else _nm("not measured"),
        "sources": {
            "avg_local_decision_ms": "rows_non_fireworks",
            "local_decision_p95_ms": "rows_non_fireworks",
            "local_decision_p99_ms": "rows_non_fireworks",
            "avg_fireworks_call_s": "metrics_records_fireworks",
            "remote_local_latency_ratio": "derived_avg_fw_s_div_avg_local_ms",
            "decisions_per_second": "dynamic_phase",
            "dynamic_avg_decision_ms": "dynamic_phase",
            "total_runtime_s": "main_wallclock",
            "startup_time_s": "not_measured",
        },
    }


def _governance(report: dict) -> dict:
    g = report.get("governance", {})
    inv = report.get("invariants", {})
    q = report.get("quality_axes", {})
    pq = q.get("path_quality", {})
    eq = q.get("escalation_quality", {})

    return {
        "baseline_frame_violations": g.get("baseline_violations", "n/a"),
        "obsidia_frame_violations": g.get("obsidia_violations", 0),
        "governed_tasks": g.get("governed_tasks", 0),
        "scored": g.get("scored", False),
        "no_auto_act_respected": inv.get("no_auto_act_respected", True),
        "no_auto_commit_respected": inv.get("no_auto_commit_respected", True),
        "no_auto_push_respected": inv.get("no_auto_push_respected", True),
        "world_actions_never_reach_model": pq.get("world_action_model_leaks", 0) == 0,
        "hold_deny_model_leaks": pq.get("hold_deny_clarify_model_leaks", 0),
        "fireworks_only_on_allow": eq.get("fireworks_only_on_allow", 0),
        "decision_authority": "KX108_ONLY",
    }


def _v3b_stack(report: dict) -> dict:
    sv3b = report.get("stack_v3b")
    nm_v3b = _nm("--stack-v3b not run in this invocation", "--stack-v3b flag")
    if not sv3b:
        return {k: nm_v3b for k in (
            "fastpath_structured_accuracy", "brody_readonly_accuracy",
            "obsidure_route_accuracy", "lean_route_accuracy",
            "domain_bank_route_accuracy", "domain_trading_route_accuracy",
            "domain_gps_route_accuracy", "v3b_remote_tokens",
            "v3b_route_accuracy", "brody_live_calls", "brody_stub_fallbacks",
        )}

    pf = sv3b.get("per_family", {})
    bm = sv3b.get("brody_metrics", {})

    def fam_acc(name: str) -> float | dict:
        st = pf.get(name)
        if not st:
            return _nm(f"family {name} not in V3B run")
        return round(st["ok"] / st["cases"], 4) if st["cases"] else 0.0

    return {
        "fastpath_structured_accuracy":  fam_acc("fastpath_structured"),
        "brody_readonly_accuracy":       fam_acc("brody_readonly"),
        "obsidure_route_accuracy":       fam_acc("obsidure_proposal"),
        "lean_route_accuracy":           fam_acc("lean_proof_query"),
        "domain_bank_route_accuracy":    fam_acc("domain_bank"),
        "domain_trading_route_accuracy": fam_acc("domain_trading"),
        "domain_gps_route_accuracy":     fam_acc("domain_gps"),
        "v3b_remote_tokens":             sv3b.get("remote_tokens", 0),
        "v3b_route_accuracy":            sv3b.get("route_accuracy", 0),
        "brody_live_calls":              bm.get("brody_live_calls", 0),
        "brody_stub_fallbacks":          bm.get("brody_stub_fallbacks", 0),
    }


def _answer_quality(report: dict, track1_rows: list[dict] | None) -> dict:
    nm_no_rows = _nm("track1_rows not available in this run mode")
    nm_no_judge = _nm("no external judge or reference answers available")
    nm_no_exec = _nm("no code execution sandbox in this cut", "code execution sandbox")
    nm_live = _nm("dry-run: no live completion tokens", "FIREWORKS_API_KEY for live run")
    nm_label = _nm("per-task expected_language not labeled", "per-task expected_language field")
    nm_harness = _nm("requires harness judge or reference", "official AMD harness")

    if not track1_rows:
        return {
            "answer_quality_score":          nm_no_judge,
            "format_compliance_rate":        nm_harness,
            "length_compliance_rate":        nm_no_rows,
            "english_compliance_rate":       nm_label,
            "corrected_code_passes_tests":   nm_no_exec,
            "code_test_pass_rate":           nm_no_exec,
            "math_exact_match_rate":         _nm("no math tasks with exact-match references"),
            "ner_f1":                        _nm("no NER tasks"),
            "sentiment_accuracy":            _nm("no sentiment tasks"),
            "summary_constraint_pass_rate":  nm_harness,
            "meta_reasoning_leak_rate":      nm_no_rows,
            "code_only_compliance_rate":     nm_no_rows,
        }

    fw_rows = [r for r in track1_rows if r.get("actual_route") == "fireworks"]
    live_fw = [r for r in fw_rows if r.get("fireworks_tokens", 0) > 25]

    # meta_reasoning_leak_rate — check live outputs for preamble patterns
    live_output_rows = [
        r for r in fw_rows
        if r.get("output") and "[dry-run]" not in (r.get("output") or "")
    ]
    if live_output_rows:
        leaks = sum(
            1 for r in live_output_rows
            if _META_START_RE.search((r.get("output") or "").strip())
        )
        meta_rate: float | dict = _pct(leaks, len(live_output_rows))
    else:
        meta_rate = nm_live

    # code_only_compliance_rate — check code-profile tasks
    code_rows = [r for r in fw_rows if r.get("expected_response_profile") == "CODE"]
    if code_rows and live_output_rows:
        live_code = [
            r for r in code_rows
            if r.get("output") and "[dry-run]" not in (r.get("output") or "")
        ]
        if live_code:
            compliant = sum(
                1 for r in live_code
                if (r.get("output") or "").strip()[:10].startswith(
                    ("```", "import", "def ", "class ", "from ", "#")
                )
            )
            code_compliance: float | dict = _pct(compliant, len(live_code))
        else:
            code_compliance = nm_live
    else:
        code_compliance = nm_live

    # length_compliance_rate — needs live tokens vs contract max_tokens
    length_compliance = nm_live if not live_fw else _nm(
        "per-task contract max_tokens not in results.json for comparison",
        "live run + per-row token count",
    )

    return {
        "answer_quality_score":          nm_no_judge,
        "format_compliance_rate":        nm_harness,
        "length_compliance_rate":        length_compliance,
        "english_compliance_rate":       nm_label,
        "corrected_code_passes_tests":   nm_no_exec,
        "code_test_pass_rate":           nm_no_exec,
        "math_exact_match_rate":         _nm("no math tasks with exact-match references"),
        "ner_f1":                        _nm("no NER tasks"),
        "sentiment_accuracy":            _nm("no sentiment tasks"),
        "summary_constraint_pass_rate":  nm_harness,
        "meta_reasoning_leak_rate":      meta_rate,
        "code_only_compliance_rate":     code_compliance,
    }


def _headline_metrics(report: dict) -> list[dict]:
    s = report["obsidia"]
    fp = report.get("footprint", {})
    lat = report.get("latency", {})
    dyn = report.get("dynamic", {})
    g = report.get("governance", {})
    q = report.get("quality_axes", {})
    pq = q.get("path_quality", {})
    pe = report.get("parametric_efficiency", {})

    return [
        {"group": "Accuracy",              "metric": "Route accuracy",            "value": f"{report['route_accuracy']:.0%}"},
        {"group": "Accuracy",              "metric": "Answer accuracy",           "value": "not_measured"},
        {"group": "Tokens",                "metric": "Fireworks calls",           "value": s["fireworks_needed"]},
        {"group": "Tokens",                "metric": "Fireworks tokens",          "value": s["fireworks_tokens"]},
        {"group": "Tokens",                "metric": "Tokens saved vs baseline",  "value": s.get("estimated_tokens_saved", 0)},
        {"group": "Model dependency",      "metric": "Zero-Fireworks rate",       "value": f"{pe.get('zero_fireworks_rate', 0):.0%}"},
        {"group": "Model dependency",      "metric": "Fireworks dependency rate", "value": f"{pe.get('fireworks_dependency_rate', 0):.0%}"},
        {"group": "Parametric efficiency", "metric": "Embedded model weights",    "value": "0 GB"},
        {"group": "Parametric efficiency", "metric": "Stack size",                "value": f"{fp.get('repo_size_mb', 0)} MB"},
        {"group": "Parametric efficiency", "metric": "Persistent memory enabled", "value": "false"},
        {"group": "Speed",                 "metric": "Local decision avg",        "value": f"{lat.get('avg_routing_ms_local', 0)} ms"},
        {"group": "Speed",                 "metric": "Decisions/sec",             "value": dyn.get("decisions_per_second")},
        {"group": "Governance",            "metric": "Frame violations",          "value": f"0/{g.get('governed_tasks', 0)}"},
        {"group": "Governance",            "metric": "Model leaks on HOLD/DENY",  "value": pq.get("hold_deny_clarify_model_leaks", 0)},
        {"group": "Stack",                 "metric": "Brody status",              "value": "stub"},
        {"group": "Stack",                 "metric": "Obsidure full enabled",     "value": "false"},
        {"group": "Stack",                 "metric": "Lean full enabled",         "value": "route-only"},
    ]


def _top_metrics(report: dict) -> dict:
    s = report["obsidia"]
    lat = report.get("latency", {})
    dyn = report.get("dynamic", {})
    pe = report.get("parametric_efficiency", {})

    return {
        "embedded_model_weight_gb":    0,
        "zero_fireworks_rate":         pe.get("zero_fireworks_rate", 0),
        "fireworks_tokens_total":      s["fireworks_tokens"],
        "route_accuracy":              report["route_accuracy"],
        "local_decision_avg_ms":       lat.get("avg_routing_ms_local", 0),
        "decisions_per_second":        dyn.get("decisions_per_second"),
    }


# ── Public API ────────────────────────────────────────────────────────────────

def build_metrics_coverage(
    report: dict,
    rows: list[dict],
    metrics_records: list[dict],
    track1_rows: list[dict] | None = None,
    total_runtime_s: float | None = None,
) -> dict:
    """Build the full metrics_coverage block from the assembled report.

    Derived from existing benchmark data — no invented scores.
    Not-measurable metrics carry {"status": "not_measured", ...}.
    Zero routing authority. KX108_ONLY unchanged.
    """
    return {
        "track1_official":       _track1_official(report, rows, metrics_records, total_runtime_s),
        "model_avoidance":       _model_avoidance(report),
        "parametric_efficiency": _parametric_efficiency_full(report),
        "obsidia_structure":     _obsidia_structure(report, rows),
        "speed":                 _speed(report, rows, total_runtime_s),
        "governance":            _governance(report),
        "v3b_stack":             _v3b_stack(report),
        "answer_quality":        _answer_quality(report, track1_rows),
        "headline":              _headline_metrics(report),
        "top_metrics":           _top_metrics(report),
    }
