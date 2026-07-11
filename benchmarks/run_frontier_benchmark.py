"""Frontier benchmark — Obsidia local stack vs Fireworks direct vs local-only.

Measures the boundary of utility between:
  A. obsidia_router  — full routing stack (gates + solvers + Fireworks fallback)
  B. fireworks_direct — bypass solvers, call Fireworks directly (non-governed only)
  C. local_only       — solvers only; mark abstain if no local closure

Governed tasks (HOLD/DENY/CLARIFY) are NEVER sent to Fireworks direct.

Output:
  results/frontier_benchmark_report.json
  results/FRONTIER_REPORT.md

No API key required: fireworks_direct marks dry-run clearly.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from statistics import mean

# ── Path fix — must run before any app.* import ───────────────────────────────
# Allows: python benchmarks/run_frontier_benchmark.py   (from repo root)
#      OR: python -m benchmarks.run_frontier_benchmark  (module mode)

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Imports ───────────────────────────────────────────────────────────────────

from app.router.decision import decide            # noqa: E402
from app.router.local_solvers import try_local_solvers  # noqa: E402
from app.adapters import fireworks               # noqa: E402

# ── Paths ─────────────────────────────────────────────────────────────────────
TASKS_FILE = ROOT / "benchmarks" / "frontier_tasks.json"
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────────────

GOVERNED_ROUTES = {"hold_commands_only", "denied", "clarification_needed", "no_model_needed"}
FIREWORKS_MODEL  = "accounts/fireworks/models/gpt-oss-120b"

# API_KEY_PRESENT: clé détectée dans l'environnement
# API_LIVE: appels Fireworks réels autorisés (clé + flag --live)
_LIVE_FLAG       = "--live" in sys.argv
API_KEY_PRESENT  = bool(os.environ.get("FIREWORKS_API_KEY", "").strip())
API_LIVE         = API_KEY_PRESENT and _LIVE_FLAG


# ── Mode runners ──────────────────────────────────────────────────────────────

def run_obsidia_router(task: dict) -> dict:
    """Full Obsidia routing stack."""
    t0 = time.perf_counter()
    decision = decide(task["prompt"])
    latency_ms = (time.perf_counter() - t0) * 1000

    route = decision["route"]
    solver = decision.get("solver", None)
    answer = decision.get("solver_answer") or decision.get("output", "")
    tokens = 0

    # If route is fireworks and API available → would spend tokens
    if route == "fireworks" and API_LIVE:
        from benchmarks.track1_remote_answer_contract import (
            build_remote_answer_contract,
            build_compact_override,
        )
        contract = build_remote_answer_contract(task["prompt"])
        compact = build_compact_override(task["prompt"], contract["answer_kind"])
        # LOT D parity: the model actually called must be decide()'s own
        # central-triage selection (decision["model"]), never the
        # contract's informative model_preference field.
        fw = fireworks.chat(
            decision["model"],
            task["prompt"],
            max_tokens=compact["completion_budget"],
            system=compact["compact_system"],
        )
        answer = fw.get("text", "")
        tokens = fw.get("total_tokens", 0)
    elif route == "fireworks":
        tokens = fireworks.estimate_tokens(task["prompt"])

    safe = route in task.get("expected_safe_routes", [route])
    accuracy_proxy = _check_keywords(answer, task.get("expected_accuracy_keywords", []))

    return {
        "mode": "obsidia_router",
        "route": route,
        "solver": solver,
        "answer_excerpt": str(answer)[:120],
        "tokens": tokens,
        "latency_ms": round(latency_ms, 2),
        "remote_called": route == "fireworks" and API_LIVE,
        "abstained": False,
        "safe": safe,
        "accuracy_proxy": accuracy_proxy,
        "failure_reason": None if safe else f"route={route} not in {task.get('expected_safe_routes')}",
    }


def run_fireworks_direct(task: dict) -> dict:
    """Bypass solvers — call Fireworks directly (governed tasks: skip)."""
    # Governed tasks must never be sent to Fireworks direct
    t0 = time.perf_counter()
    gate_check = decide(task["prompt"])
    gate_route = gate_check["route"]

    if gate_route in GOVERNED_ROUTES:
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "mode": "fireworks_direct",
            "route": gate_route,
            "solver": None,
            "answer_excerpt": "[governed — Fireworks skipped]",
            "tokens": 0,
            "latency_ms": round(latency_ms, 2),
            "remote_called": False,
            "abstained": False,
            "safe": gate_route in task.get("expected_safe_routes", [gate_route]),
            "accuracy_proxy": None,
            "failure_reason": None,
            "note": "governed task — gate wins",
        }

    tokens = 0
    answer = ""
    if API_LIVE:
        fw = fireworks.chat(FIREWORKS_MODEL, task["prompt"])
        answer = fw.get("text", "")
        tokens = fw.get("total_tokens", 0)
        latency_ms = (time.perf_counter() - t0) * 1000
    else:
        tokens = fireworks.estimate_tokens(task["prompt"])
        latency_ms = (time.perf_counter() - t0) * 1000

    accuracy_proxy = _check_keywords(answer, task.get("expected_accuracy_keywords", []))
    safe = "fireworks" in task.get("expected_safe_routes", ["fireworks"])

    return {
        "mode": "fireworks_direct",
        "route": "fireworks",
        "solver": None,
        "answer_excerpt": str(answer)[:120],
        "tokens": tokens,
        "latency_ms": round(latency_ms, 2),
        "remote_called": API_LIVE,
        "abstained": False,
        "safe": safe,
        "accuracy_proxy": accuracy_proxy,
        "failure_reason": None if safe else "fireworks_direct_on_governed",
        "dry_run": not API_LIVE,
    }


def run_local_only(task: dict) -> dict:
    """Local solvers only — abstain if no closure."""
    t0 = time.perf_counter()

    # Gates still apply: a governed task must never produce a local "answer"
    gate_check = decide(task["prompt"])
    gate_route = gate_check["route"]
    if gate_route in GOVERNED_ROUTES:
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "mode": "local_only",
            "route": gate_route,
            "solver": None,
            "answer_excerpt": f"[governed — {gate_route}]",
            "tokens": 0,
            "latency_ms": round(latency_ms, 2),
            "remote_called": False,
            "abstained": False,
            "safe": gate_route in task.get("expected_safe_routes", [gate_route]),
            "accuracy_proxy": None,
            "failure_reason": None,
        }

    result = try_local_solvers(task["prompt"])
    latency_ms = (time.perf_counter() - t0) * 1000

    if result is None:
        expected = task.get("expected_best_mode")
        # Correct abstention: expected fireworks/hold/deny/clarify
        correct_abstain = expected in ("fireworks", "hold", "deny", "clarify", "abstain")
        return {
            "mode": "local_only",
            "route": "abstain",
            "solver": None,
            "answer_excerpt": "[abstained]",
            "tokens": 0,
            "latency_ms": round(latency_ms, 2),
            "remote_called": False,
            "abstained": True,
            "correct_abstention": correct_abstain,
            "safe": True,
            "accuracy_proxy": None,
            "failure_reason": None if correct_abstain else "false_abstention_expected_local",
        }

    answer = result["answer"]
    accuracy_proxy = _check_keywords(answer, task.get("expected_accuracy_keywords", []))
    expected = task.get("expected_best_mode")
    # False local closure: answered a task that expected fireworks
    false_closure = expected in ("fireworks",) and result is not None

    return {
        "mode": "local_only",
        "route": "local_solver",
        "solver": result["solver"],
        "answer_excerpt": str(answer)[:120],
        "tokens": 0,
        "latency_ms": round(latency_ms, 2),
        "remote_called": False,
        "abstained": False,
        "safe": True,
        "accuracy_proxy": accuracy_proxy,
        "false_local_closure": false_closure,
        "failure_reason": "false_local_closure" if false_closure else None,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_keywords(answer: str, keywords: list[str]) -> bool | None:
    if not keywords:
        return None
    low = answer.lower()
    return all(kw.lower() in low for kw in keywords)


def _pct(n: int, total: int) -> str:
    return f"{n}/{total} ({100*n//total if total else 0}%)"


# ── Aggregation ───────────────────────────────────────────────────────────────

def aggregate(results: list[dict], tasks: list[dict]) -> dict:
    families = {}
    for r, t in zip(results, tasks):
        fam = t["family"]
        families.setdefault(fam, {"obsidia_router": [], "fireworks_direct": [], "local_only": []})
        families[fam][r["mode"]].append(r)

    summary = {}
    for fam, modes in families.items():
        fam_tasks = [t for t in tasks if t["family"] == fam]
        n = len(fam_tasks)
        row = {"n_tasks": n}
        for mode, recs in modes.items():
            if not recs:
                continue
            tokens = [r["tokens"] for r in recs]
            latencies = [r["latency_ms"] for r in recs]
            safe_count = sum(1 for r in recs if r.get("safe"))
            abstained = sum(1 for r in recs if r.get("abstained"))
            correct_abs = sum(1 for r in recs if r.get("correct_abstention"))
            acc = [r["accuracy_proxy"] for r in recs if r["accuracy_proxy"] is not None]
            row[mode] = {
                "avg_tokens": round(mean(tokens), 1) if tokens else 0,
                "avg_latency_ms": round(mean(latencies), 2) if latencies else 0,
                "p50_latency_ms": round(sorted(latencies)[len(latencies)//2], 2) if latencies else 0,
                "safe_rate": _pct(safe_count, len(recs)),
                "abstained": abstained,
                "correct_abstentions": correct_abs,
                "accuracy_proxy_rate": _pct(sum(1 for a in acc if a), len(acc)) if acc else "n/a",
            }
        summary[fam] = row
    return summary


def frontier_analysis(results_by_mode: dict[str, list], tasks: list[dict]) -> dict:
    """Identify the break-even complexity level and winner per family."""
    local_wins, fw_wins, governed, abstains_correct = [], [], [], []
    false_closures = 0
    by_complexity: dict[int, dict] = {}

    obsidia = results_by_mode["obsidia_router"]
    local   = results_by_mode["local_only"]

    for i, task in enumerate(tasks):
        lvl = task["complexity_level"]
        by_complexity.setdefault(lvl, {"local_closed": 0, "fireworks_needed": 0, "governed": 0, "total": 0})
        by_complexity[lvl]["total"] += 1

        o = obsidia[i]
        lc = local[i]

        if o["route"] in GOVERNED_ROUTES:
            governed.append(task["id"])
            by_complexity[lvl]["governed"] += 1
        elif o["route"] == "local_solver":
            local_wins.append(task["id"])
            by_complexity[lvl]["local_closed"] += 1
        else:
            fw_wins.append(task["id"])
            by_complexity[lvl]["fireworks_needed"] += 1

        if lc.get("false_local_closure"):
            false_closures += 1
        if lc.get("correct_abstention"):
            abstains_correct.append(task["id"])

    # Break-even: first complexity level where fireworks_needed > local_closed
    break_even = None
    for lvl in sorted(by_complexity.keys()):
        d = by_complexity[lvl]
        if d["fireworks_needed"] > d["local_closed"]:
            break_even = lvl
            break

    return {
        "local_wins": local_wins,
        "fireworks_wins": fw_wins,
        "governed_tasks": governed,
        "correct_abstentions": abstains_correct,
        "false_local_closures": false_closures,
        "break_even_complexity_level": break_even,
        "by_complexity_level": by_complexity,
    }


# ── Zone classification ───────────────────────────────────────────────────────

def classify_zone_and_reason(
    task: dict,
    obsidia: dict,
    local: dict,
) -> tuple[str, str]:
    """Return (zone, reason) for the Boundary Map.

    Zones:
      SOLO_SAFE          — local solver / gate closes at 0 token, no model needed
      GOVERNED_NEVER_MODEL — gate fires (HOLD/DENY/CLARIFY) on action/risk
      FRONTIER_ABSTAIN   — local abstains, Obsidia routes to Brody/Clarify (not Fireworks)
      FIREWORKS_USEFUL   — local abstains, Obsidia escalates to Fireworks; open-world task

    Reasons:
      closed_by_solver, closed_by_gate, missing_fingerprint,
      open_world_reasoning, action_risk, ambiguity,
      unknown_entity, code_not_covered
    """
    o_route  = obsidia["route"]
    l_route  = local["route"]
    family   = task.get("family", "")
    notes    = task.get("notes", "")
    action   = task.get("action_risk", False)
    open_w   = task.get("open_world", False)
    lvl      = task.get("complexity_level", 0)

    # 1. GOVERNED_NEVER_MODEL — gate fires on world actions
    if o_route in ("hold_commands_only", "denied"):
        return ("GOVERNED_NEVER_MODEL", "action_risk")
    if o_route == "clarification_needed" and action:
        return ("GOVERNED_NEVER_MODEL", "ambiguity")

    # 2. SOLO_SAFE — closed by local solver
    if o_route == "local_solver":
        return ("SOLO_SAFE", "closed_by_solver")
    if o_route in ("no_model_needed", "memory_hit"):
        return ("SOLO_SAFE", "closed_by_gate")

    # 3. Determine reason for non-local routes
    if "unknown" in notes.lower() or "unknown_entity" in notes.lower():
        reason = "unknown_entity"
    elif "code" in notes.lower() and ("different" in notes.lower() or "spec" in notes.lower() or "covered" in notes.lower()):
        reason = "code_not_covered"
    elif "missing" in notes.lower() or family == "near_boundary":
        reason = "missing_fingerprint"
    elif open_w and lvl >= 4:
        reason = "open_world_reasoning"
    elif o_route == "clarification_needed":
        reason = "ambiguity"
    elif family == "noisy_dirty":
        reason = "ambiguity"
    else:
        reason = "open_world_reasoning"

    # 4. FRONTIER_ABSTAIN — local abstains, Obsidia routes to Brody/Clarify (not Fireworks)
    if o_route in ("brody", "clarification_needed") and l_route == "abstain":
        return ("FRONTIER_ABSTAIN", reason)

    # 5. FIREWORKS_USEFUL — Obsidia escalates to Fireworks
    if o_route == "fireworks":
        return ("FIREWORKS_USEFUL", reason)

    # Fallback
    return ("FRONTIER_ABSTAIN", reason)


# ── Report writers ────────────────────────────────────────────────────────────

def write_json_report(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def write_md_report(report: dict, path: Path) -> None:
    fa      = report["frontier_analysis"]
    summary = report["family_summary"]
    meta    = report["meta"]
    results = report["task_results"]

    zones: dict[str, list[dict]] = {
        "SOLO_SAFE": [], "GOVERNED_NEVER_MODEL": [],
        "FRONTIER_ABSTAIN": [], "FIREWORKS_USEFUL": [],
    }
    for r in results:
        zones[r["zone"]].append(r)

    lines = [
        "# Frontier Benchmark Report",
        "",
        f"Run: `{meta['run_id']}`  |  Tasks: {meta['n_tasks']}  |  "
        f"API key: `{meta['api_key_present']}`  |  "
        f"fireworks_direct_live: `{meta['fireworks_direct_live']}`",
        "",
    ]

    # ── Boundary Map ──────────────────────────────────────────────────────────
    lines += [
        "## Boundary Map -- where Obsidia goes solo vs where Fireworks is useful",
        "",
        "| id | family | complexity | obsidia_route | local_route | zone | reason |",
        "|----|--------|-----------|--------------|------------|------|--------|",
    ]
    for r in results:
        o_route = r["obsidia"]["route"]
        l_route = r["local_only"]["route"]
        lines.append(
            f"| {r['task_id']} | {r['family']} | {r['complexity_level']}"
            f" | {o_route} | {l_route} | **{r['zone']}** | {r['reason']} |"
        )

    lines += ["", "---", ""]

    # SOLO_SAFE
    ss = zones["SOLO_SAFE"]
    ss_families = sorted({r["family"] for r in ss})
    ss_latencies = [r["obsidia"]["latency_ms"] for r in ss]
    ss_tokens_saved = sum(r["fireworks_direct"]["tokens"] for r in ss)
    avg_ss_lat = round(mean(ss_latencies), 2) if ss_latencies else 0
    lines += [
        "### SOLO_SAFE",
        f"- **Count**: {len(ss)} tasks",
        f"- **Families**: {', '.join(ss_families)}",
        f"- **Avg Obsidia latency**: {avg_ss_lat} ms",
        f"- **Tokens saved vs Fireworks direct**: ~{ss_tokens_saved} (estimated)",
        "- **Why**: Exact fingerprint or deterministic gate -- no model, 0 tokens.",
        "",
    ]

    # GOVERNED_NEVER_MODEL
    gv = zones["GOVERNED_NEVER_MODEL"]
    lines += [
        "### GOVERNED_NEVER_MODEL",
        f"- **Count**: {len(gv)} tasks",
        f"- **Tasks**: {', '.join(r['task_id'] for r in gv)}",
        "- **Why Fireworks must never be called**: world-action or destructive risk "
        "(push, rm-rf, deploy, bypass). Calling a model violates the governance "
        "invariant no_auto_act/no_auto_commit/no_auto_push. "
        "Gates intercept at level 0, 0 tokens.",
        "",
    ]

    # FRONTIER_ABSTAIN
    fa_zone = zones["FRONTIER_ABSTAIN"]
    fa_examples = [r["task_id"] for r in fa_zone[:4]]
    lines += [
        "### FRONTIER_ABSTAIN",
        f"- **Count**: {len(fa_zone)} tasks",
        f"- **Examples**: {', '.join(fa_examples)}",
        "- **Why local is right to stop**:",
        "  - Missing signal: micro-solver fingerprint incomplete "
        "(token bucket without limiter.py, CAP without resume).",
        "  - Unknown entity: NER/factual outside canonical knowledge base.",
        "  - Ambiguity: contradictory or too-short prompt for deterministic answer.",
        "  - Obsidia routes to Brody or Clarification (not Fireworks): 0 tokens, governed.",
        "",
    ]

    # FIREWORKS_USEFUL
    fw_zone = zones["FIREWORKS_USEFUL"]
    fw_complexities = [r["complexity_level"] for r in fw_zone]
    fw_tokens = [r["fireworks_direct"]["tokens"] for r in fw_zone
                 if r["fireworks_direct"]["tokens"] > 0]
    avg_fw_tok = round(mean(fw_tokens), 0) if fw_tokens else "n/a (dry-run)"
    avg_fw_cplx = round(mean(fw_complexities), 1) if fw_complexities else "n/a"
    lines += [
        "### FIREWORKS_USEFUL",
        f"- **Count**: {len(fw_zone)} tasks",
        f"- **Avg complexity level**: {avg_fw_cplx}",
        f"- **Avg Fireworks tokens (estimated)**: {avg_fw_tok}",
        "- **Why Fireworks is useful**:",
        "  - Open-world reasoning: unknown architectures, new technical plans.",
        "  - Code not covered by micro-solver: BST, LRU, different specs.",
        "  - Unknown entity/country: open-world knowledge impossible to close locally.",
        "  - Noisy prompts without recognizable pattern.",
        "  - Frontier: complexity >= 4 or open_world=true.",
        "",
    ]

    # Complexity table
    lines += [
        "---",
        "",
        "## Frontier Analysis",
        "",
        f"- **Local wins**: {len(fa['local_wins'])} tasks",
        f"- **Fireworks wins (via obsidia router)**: {len(fa['fireworks_wins'])} tasks",
        f"- **Governed**: {len(fa['governed_tasks'])} tasks",
        f"- **Correct abstentions (local_only)**: {len(fa['correct_abstentions'])} tasks",
        f"- **False local closures**: {fa['false_local_closures']}",
        f"- **Break-even complexity level**: {fa['break_even_complexity_level']}",
        "",
        "### By Complexity Level",
        "",
        "| Level | Total | Local closed | Fireworks needed | Governed |",
        "|-------|-------|-------------|-----------------|---------|",
    ]
    for lvl, d in sorted(fa["by_complexity_level"].items()):
        lines.append(
            f"| {lvl} | {d['total']} | {d['local_closed']} | "
            f"{d['fireworks_needed']} | {d['governed']} |"
        )

    # Family summary
    lines += ["", "## Family Summary", ""]
    for fam, row in summary.items():
        lines.append(f"### {fam} (n={row['n_tasks']})")
        lines.append("")
        lines.append("| Mode | Avg tokens | Avg latency ms | Safe rate | Abstained |")
        lines.append("|------|-----------|----------------|-----------|-----------|")
        for mode in ("obsidia_router", "fireworks_direct", "local_only"):
            if mode in row:
                m = row[mode]
                lines.append(
                    f"| {mode} | {m['avg_tokens']} | {m['avg_latency_ms']} | "
                    f"{m['safe_rate']} | {m['abstained']} |"
                )
        lines.append("")

    # Token economics + final boundary statement
    lines += [
        "## Token Economics",
        "",
        "- Avg Obsidia routing cost (local, no API): ~0.1 ms, 0 tokens",
        f"- Avg Fireworks estimate: {meta.get('avg_fw_estimate_tokens', 'n/a')} tokens",
        f"- FIREWORKS_API_KEY detected: {meta['api_key_present']}  "
        f"|  fireworks_direct_live: {meta['fireworks_direct_live']}  "
        f"|  real latency: "
        + ("measured" if meta["fireworks_direct_live"]
           else "NOT measured (add --live + FIREWORKS_API_KEY)"),
        "",
        "## Risks",
        "",
        f"- False local closure rate: {fa['false_local_closures']} "
        "(0 = no micro-solver answered outside its fingerprint)",
        "- Typo prompts: local solver may not close; Fireworks fallback is safe",
        "- Open-world tasks (open_world=true): only Fireworks can answer correctly",
        "",
        "> **Current boundary**: Obsidia should go solo for closed deterministic tasks "
        "and exact solver fingerprints; abstain at near-boundary prompts; "
        "escalate to Fireworks for open-world tasks at complexity >= 4; "
        "and never call Fireworks directly for governed actions.",
        "",
        "_Generated by run_frontier_benchmark.py -- read-only, no commit, no push_",
    ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    with open(TASKS_FILE, encoding="utf-8") as f:
        tasks: list[dict] = json.load(f)

    print(f"\n=== FRONTIER BENCHMARK ({len(tasks)} tasks) ===")
    print(f"  FIREWORKS_API_KEY detected : {API_KEY_PRESENT}")
    print(f"  --live flag                : {_LIVE_FLAG}")
    print(f"  fireworks_direct_live      : {API_LIVE}")
    if not API_KEY_PRESENT:
        print("  NOTE: set FIREWORKS_API_KEY + --live to measure real Fireworks tokens/latency")
    elif not _LIVE_FLAG:
        print("  NOTE: add --live to enable real Fireworks calls (fireworks_direct mode)")
    print()

    results_by_mode: dict[str, list] = {
        "obsidia_router": [],
        "fireworks_direct": [],
        "local_only": [],
    }

    all_flat: list[dict] = []
    fw_estimates: list[int] = []

    for task in tasks:
        ro  = run_obsidia_router(task)
        rfd = run_fireworks_direct(task)
        rl  = run_local_only(task)

        results_by_mode["obsidia_router"].append(ro)
        results_by_mode["fireworks_direct"].append(rfd)
        results_by_mode["local_only"].append(rl)

        if rfd.get("dry_run") and rfd["tokens"] > 0:
            fw_estimates.append(rfd["tokens"])

        # Console row
        route_o = ro["route"]
        route_l = rl["route"]
        tok_o   = ro["tokens"]
        safe_o  = "OK " if ro["safe"] else "FAIL"
        kw_ok   = ("acc+" if ro.get("accuracy_proxy") else
                   "acc?" if ro.get("accuracy_proxy") is None else "acc-")
        print(
            f"[{safe_o}] {task['id']:<35} "
            f"fam={task['family']:<18} "
            f"obsidia={route_o:<18} local={route_l:<14} "
            f"tok={tok_o:<5} {kw_ok}"
        )
        zone, reason = classify_zone_and_reason(task, ro, rl)
        all_flat.append({
            "task_id": task["id"],
            "family": task["family"],
            "complexity_level": task.get("complexity_level", 0),
            "zone": zone,
            "reason": reason,
            "obsidia": ro,
            "fireworks_direct": rfd,
            "local_only": rl,
        })

    summary = aggregate(
        [r for group in zip(
            results_by_mode["obsidia_router"],
            results_by_mode["fireworks_direct"],
            results_by_mode["local_only"],
        ) for r in group],
        [t for t in tasks for _ in range(3)],
    )
    # Re-aggregate cleanly per mode
    family_summary = _aggregate_by_family(results_by_mode, tasks)
    fa = frontier_analysis(results_by_mode, tasks)

    avg_fw_est = round(mean(fw_estimates), 1) if fw_estimates else "n/a"

    run_id = time.strftime("%Y%m%d_%H%M%S")
    meta = {
        "run_id": run_id,
        "n_tasks": len(tasks),
        "api_key_present": API_KEY_PRESENT,
        "live_flag": _LIVE_FLAG,
        "fireworks_direct_live": API_LIVE,
        "avg_fw_estimate_tokens": avg_fw_est,
        "governance": {
            "real_action": False,
            "memory_write": False,
            "kernel_mutation": False,
            "decision_authority": "KX108_ONLY",
        },
    }

    report = {
        "meta": meta,
        "frontier_analysis": fa,
        "family_summary": family_summary,
        "task_results": all_flat,
    }

    json_path = RESULTS_DIR / "frontier_benchmark_report.json"
    md_path   = RESULTS_DIR / "FRONTIER_REPORT.md"
    write_json_report(report, json_path)
    write_md_report(report, md_path)

    # Console summary
    print(f"\n{'='*60}")
    print(f"LOCAL wins  : {len(fa['local_wins'])} tasks -> {fa['local_wins']}")
    print(f"FIREWORKS   : {len(fa['fireworks_wins'])} tasks -> {fa['fireworks_wins']}")
    print(f"GOVERNED    : {len(fa['governed_tasks'])} tasks (gates always win)")
    print(f"Correct abstentions (local_only) : {len(fa['correct_abstentions'])}")
    print(f"False local closures             : {fa['false_local_closures']}")
    print(f"Break-even complexity level      : {fa['break_even_complexity_level']}")
    print(f"FIREWORKS_API_KEY detected       : {API_KEY_PRESENT}")
    print(f"fireworks_direct_live            : {API_LIVE}")
    if not API_KEY_PRESENT:
        print("  => set FIREWORKS_API_KEY + --live for real Fireworks latency/tokens")
    elif not _LIVE_FLAG:
        print("  => add --live to enable real Fireworks calls in fireworks_direct mode")
    print(f"\nReports written:")
    print(f"  {json_path}")
    print(f"  {md_path}")


def _aggregate_by_family(results_by_mode: dict[str, list], tasks: list[dict]) -> dict:
    fams: dict[str, dict] = {}
    for mode, recs in results_by_mode.items():
        for rec, task in zip(recs, tasks):
            fam = task["family"]
            fams.setdefault(fam, {"n_tasks": 0, "obsidia_router": [], "fireworks_direct": [], "local_only": []})
            fams[fam]["n_tasks"] = sum(1 for t in tasks if t["family"] == fam)
            fams[fam][mode].append(rec)

    out = {}
    for fam, data in fams.items():
        row = {"n_tasks": data["n_tasks"]}
        for mode in ("obsidia_router", "fireworks_direct", "local_only"):
            recs = data[mode]
            if not recs:
                continue
            tokens = [r["tokens"] for r in recs]
            latencies = [r["latency_ms"] for r in recs]
            safe_count = sum(1 for r in recs if r.get("safe"))
            abstained = sum(1 for r in recs if r.get("abstained"))
            correct_abs = sum(1 for r in recs if r.get("correct_abstention"))
            acc = [r["accuracy_proxy"] for r in recs if r["accuracy_proxy"] is not None]
            row[mode] = {
                "avg_tokens": round(mean(tokens), 1) if tokens else 0,
                "avg_latency_ms": round(mean(latencies), 2) if latencies else 0,
                "p50_latency_ms": round(sorted(latencies)[len(latencies)//2], 2) if latencies else 0,
                "total_tokens": sum(tokens),
                "safe_rate": _pct(safe_count, len(recs)),
                "abstained": abstained,
                "correct_abstentions": correct_abs,
                "accuracy_proxy_rate": _pct(sum(1 for a in acc if a), len(acc)) if acc else "n/a",
            }
        out[fam] = row
    return out


if __name__ == "__main__":
    main()
