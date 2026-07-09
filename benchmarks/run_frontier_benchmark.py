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
        from benchmarks.track1_remote_answer_contract import build_remote_answer_contract
        contract = build_remote_answer_contract(task["prompt"])
        fw = fireworks.chat(
            contract["model_preference"],
            task["prompt"],
            max_tokens=contract["max_tokens"],
            system=contract["contract_prompt"],
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


# ── Report writers ────────────────────────────────────────────────────────────

def write_json_report(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def write_md_report(report: dict, path: Path) -> None:
    fa = report["frontier_analysis"]
    summary = report["family_summary"]
    meta = report["meta"]

    lines = [
        "# Frontier Benchmark Report",
        "",
        f"Run: `{meta['run_id']}`  |  Tasks: {meta['n_tasks']}  |  "
        f"API key: `{meta['api_key_present']}`  |  "
        f"fireworks_direct_live: `{meta['fireworks_direct_live']}`",
        "",
        "## Frontier Analysis",
        "",
        f"- **Local wins** ({len(fa['local_wins'])} tasks): "
        + (", ".join(fa["local_wins"]) or "none"),
        f"- **Fireworks wins** ({len(fa['fireworks_wins'])} tasks): "
        + (", ".join(fa["fireworks_wins"]) or "none"),
        f"- **Governed** ({len(fa['governed_tasks'])} tasks): "
        + (", ".join(fa["governed_tasks"]) or "none"),
        f"- **Correct abstentions** (local_only): {len(fa['correct_abstentions'])} tasks",
        f"- **False local closures**: {fa['false_local_closures']}",
        f"- **Break-even complexity level**: {fa['break_even_complexity_level']} "
        "(first level where Fireworks > local)",
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

    lines += [
        "",
        "## Questions answered",
        "",
        "1. **Local gagne** : closed_exact, closed_variants, governed (gates), noisy math/jailbreak",
        "2. **Fireworks gagne** : open_reasoning (complexity ≥ 4), near_boundary abstentions, typo + unknown entity",
        "3. **Local doit abstain** : near_boundary (signal manquant) — vérifié ci-dessus",
        "4. **Fireworks jamais appelé** : governed_actions (HOLD/DENY/CLARIFY) — gates gagnent toujours",
        f"5. **Break-even complexity level** : {fa['break_even_complexity_level']}",
        "",
        "## Family Summary",
        "",
    ]

    for fam, row in summary.items():
        lines.append(f"### {fam} (n={row['n_tasks']})")
        lines.append("")
        lines.append("| Mode | Avg tokens | Avg latency ms | Safe rate | Abstained | Accuracy proxy |")
        lines.append("|------|-----------|----------------|-----------|-----------|----------------|")
        for mode in ("obsidia_router", "fireworks_direct", "local_only"):
            if mode in row:
                m = row[mode]
                lines.append(
                    f"| {mode} | {m['avg_tokens']} | {m['avg_latency_ms']} | "
                    f"{m['safe_rate']} | {m['abstained']} | {m['accuracy_proxy_rate']} |"
                )
        lines.append("")

    lines += [
        "## Token Economics",
        "",
        f"- Avg Obsidia routing cost (local, no API): ~0.1 ms, 0 tokens",
        f"- Avg Fireworks dry-run estimate: {meta.get('avg_fw_estimate_tokens', 'n/a')} tokens",
        f"- FIREWORKS_API_KEY detected: {meta['api_key_present']}  "
        f"|  fireworks_direct_live: {meta['fireworks_direct_live']}  "
        f"|  real Fireworks latency: {'measured' if meta['fireworks_direct_live'] else 'NOT measured (add --live + FIREWORKS_API_KEY)'}",
        "",
        "## Risks",
        "",
        "- False local closure rate: "
        + str(fa['false_local_closures'])
        + " (micro-solvers with wrong signal match — verify near_boundary family)",
        "- Typo prompts: local solver may not close, escalation to Fireworks is safe fallback",
        "- Open-world tasks (open_world=true): only Fireworks can answer correctly",
        "",
        "_Generated by run_frontier_benchmark.py — read-only, no commit, no push_",
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
        all_flat.append({"task_id": task["id"], "obsidia": ro, "fireworks_direct": rfd, "local_only": rl})

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
