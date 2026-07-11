"""Track 1 official runner — short answers + results.json + receipts_internal.json.

Transforme les décisions Obsidia (déjà calculées par le pipeline principal) en deux
fichiers de sortie :

  results/results.json
    Format public : une answer courte par tâche, tokens, route, latence.
    Ne contient JAMAIS : dump IR, receipts gouvernance, KX108_ONLY, real_action, etc.

  results/receipts_internal.json
    Traçabilité complète : gate, IR fields, invariants, route correctness.
    Non soumis au harness. Utilisé pour audit / démo.

Usage direct (standalone, bypass run_benchmark.py) :
  python -m benchmarks.track1_runner [--tasks-file benchmarks/tasks.json]

Usage intégré (recommandé) :
  python benchmarks/run_benchmark.py --track1-official [--tasks-file ...]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from benchmarks.track1_response_profile import build_response_profile_telemetry

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Gouvernance immuable (interne uniquement) ─────────────────────────────────

_INTERNAL_GOVERNANCE = {
    "real_action": False,
    "memory_write": False,
    "kernel_mutation": False,
    "emits_act": False,
    "decision_authority": "KX108_ONLY",
}

# ── Transformation output par route ──────────────────────────────────────────

def track1_answer(row: dict) -> str:
    """Produit une réponse courte lisible pour le harness Track 1.

    Règles :
    - Jamais de dump IR (UnifiedInputIR / intent_type / ...)
    - Jamais de texte de gouvernance interne dans la réponse officielle
    - Jamais de "[brody-stub]" brut
    - Fireworks : réponse modèle intacte
    - Memory : contenu du corpus (déjà pertinent)
    - HOLD/DENY/CLARIFY : message court lisible
    - no_model_needed : statut court sans trace IR
    """
    route = row["actual_route"]
    output = row.get("output", "")
    intent = row.get("intent_type", "unknown")
    missing = row.get("missing") or []
    matched = row.get("gate_matched") or "action"
    memory = row.get("memory_entry")

    if route == "no_model_needed":
        if intent == "status":
            return "System operational. Obsidia Router active - deterministic pre-inference pipeline."
        return "Request resolved locally. No remote model required."

    if route == "hold_commands_only":
        return (
            f"HOLD: '{matched}' requires explicit human approval. "
            "No action has been taken. Provide approval to proceed."
        )

    if route == "denied":
        return f"DENIED: '{matched}' is outside the authorized frame. Request refused."

    if route == "clarification_needed":
        missing_str = ", ".join(missing) if missing else "intent"
        return f"Clarification needed. Missing: {missing_str}. Please specify your intent more precisely."

    if route == "memory_hit":
        if memory and isinstance(memory, str):
            return memory
        return output or "Memory: no entry found."

    if route == "local_solver":
        # Reponse deterministe locale (sentiment/math) : la valeur elle-meme.
        return output or "Local solver produced no answer."

    if route == "brody":
        # Si l'output est du texte brody-stub interne, on le remplace par un message propre
        if output and not output.startswith("[brody-stub]"):
            return output  # réponse Brody live réelle
        topic = row.get("topic_name", "general")
        return (
            f"[Brody] {intent.title()} answered locally via governed organ. "
            f"Topic: {topic}. No remote inference used."
        )

    if route == "fireworks":
        # Réponse modèle réelle : on la retourne intacte
        # En dry-run, "[dry-run]" indique l'absence de clé API
        return output or "[error] No model response captured."

    # Routes V3B (ne sont normalement pas dans tasks.json principal, mais gestion défensive)
    if route == "obsidure_route_only":
        return "Obsidure: proposal-only routing. Non-sovereign. No remote inference."
    if route == "lean_route_only":
        return "Lean: formal proof surface check. No remote inference."
    if route == "domain_bridge":
        return f"Domain: governed domain signal ({row.get('target_layer', 'domain')}). Human review required."

    # Fallback
    return f"Route: {route}."


# ── Normalisation input harness AMD ──────────────────────────────────────────

def normalize_task(task: dict) -> dict:
    """Accepte les deux schemas d'entree :
    officiel AMD  : {"task_id": ..., "prompt": ...}
    interne       : {"id": ..., "request": ...}
    """
    return {
        **task,
        "id": task.get("task_id") or task.get("id"),
        "request": task.get("prompt") or task.get("request"),
    }


# ── Construction des deux fichiers de sortie ──────────────────────────────────

def build_official_results(track1_rows: list[dict]) -> list[dict]:
    """Format officiel harness AMD : liste JSON simple, rien d'autre.

    [{"task_id": "...", "answer": "..."}, ...]
    Toutes les metriques restent dans benchmark_report.json / receipts.
    """
    return [
        {"task_id": row["id"], "answer": track1_answer(row)}
        for row in track1_rows
    ]


def build_results(track1_rows: list[dict]) -> dict:
    """Construit le dict results.json (public, sans gouvernance)."""
    tasks_out = []
    total_tokens = 0

    for row in track1_rows:
        tokens = row.get("fireworks_tokens", 0)
        total_tokens += tokens
        tasks_out.append({
            "id": row["id"],
            "answer": track1_answer(row),
            "route": row["actual_route"],
            "level": row.get("level", 0),
            "tokens_used": tokens,
            "fireworks_model": row.get("actual_model_used") or row.get("model"),
            "latency_ms": row.get("routing_latency_ms", 0.0),
            "route_correct": row.get("route_correct", False),
        })

    total = len(track1_rows)
    correct = sum(1 for r in track1_rows if r.get("route_correct", False))

    return {
        "format_version": "track1_v1",
        "total_tasks": total,
        "route_accuracy": round(correct / total, 4) if total else 0.0,
        "remote_calls": sum(1 for r in track1_rows if r["actual_route"] == "fireworks"),
        "remote_calls_avoided": sum(1 for r in track1_rows if r.get("remote_call_avoided", True)),
        "tokens_used_total": total_tokens,
        "tasks": tasks_out,
    }


def build_receipts(track1_rows: list[dict], extra: dict | None = None) -> dict:
    """Construit les receipts_internal.json (gouvernance complète, non soumis au harness)."""
    tasks_out = []
    for row in track1_rows:
        # Build Brody-like response profile telemetry from observed answer.
        # bounded_remote_call=True only when route==fireworks AND a profile was
        # applied before the call — distinguishing it from remote_call_avoided tasks.
        answer_text = track1_answer(row)
        expected_profile = row.get("expected_response_profile") or "SHORT"
        is_bounded_remote = (
            row["actual_route"] == "fireworks"
            and row.get("expected_response_profile") is not None
        )
        profile_telemetry = build_response_profile_telemetry(
            expected_profile, answer_text, bounded_remote_call=is_bounded_remote
        )

        contract = row.get("remote_answer_contract")
        receipt_row: dict = {
            "id": row["id"],
            "request": row["request"],
            "expected_route": row.get("expected_route"),
            "actual_route": row["actual_route"],
            "route_correct": row.get("route_correct", False),
            "gate_verdict": row.get("gate_verdict"),
            "gate_matched": row.get("gate_matched"),
            "level": row.get("level", 0),
            "model": row.get("model"),
            "intent_type": row.get("intent_type"),
            "target_layer": row.get("target_layer"),
            "missing": row.get("missing", []),
            "fireworks_tokens": row.get("fireworks_tokens", 0),
            "prompt_tokens": row.get("prompt_tokens", 0),
            "completion_tokens": row.get("completion_tokens", 0),
            "remote_call_avoided": row.get("remote_call_avoided", True),
            "routing_latency_ms": row.get("routing_latency_ms", 0.0),
            "actual_model_used": row.get("actual_model_used") or row.get("model"),
            # LOT E — doctrine (see app.metrics.triage_metrics):
            #   selected_model            = model chosen by the central triage
            #                                authority (== row["model"] on a
            #                                fireworks row; None otherwise)
            #   actual_model_used         = model really transmitted to
            #                                fireworks.chat() (field above)
            #   contract_model_preference = the remote answer contract's OLD
            #                                informative field — kept for
            #                                back-compat only, never selects
            #                                the call target (LOT D)
            #   selected_rung/selection_reason = the triage's own trace
            "selected_model": row.get("model") if row["actual_route"] == "fireworks" else None,
            "selected_rung": row.get("selected_rung"),
            "selection_reason": row.get("selection_reason"),
            "ladder_size": row.get("ladder_size"),
            "contract_model_preference": (
                contract["model_preference"]
                if contract and row["actual_route"] == "fireworks"
                else None
            ),
            "raw_prompt_chars": row.get("raw_prompt_chars"),
            "system_prompt_chars": row.get("system_prompt_chars"),
            "compression_applied": row.get("compression_applied"),
            "compressed_prompt_chars": row.get("compressed_prompt_chars"),
            # Remote answer contract labels (fireworks rows only)
            "contract_kind": contract["answer_kind"] if contract else None,
            "model_matrix_calibrated": contract["model_matrix_calibrated"] if contract else False,
            "calibration_source": contract["calibration_source"] if contract else None,
            "budget_headroom_policy": contract["budget_headroom_policy"] if contract else None,
            **profile_telemetry,
        }
        if contract:
            receipt_row["remote_answer_contract"] = contract
        tasks_out.append(receipt_row)

    total = len(track1_rows)
    correct = sum(1 for r in track1_rows if r.get("route_correct", False))

    receipt: dict = {
        "governance": _INTERNAL_GOVERNANCE,
        "run_id": extra.get("run_id") if extra else None,
        "total_tasks": total,
        "route_accuracy": round(correct / total, 4) if total else 0.0,
        "remote_tokens": sum(r.get("fireworks_tokens", 0) for r in track1_rows),
        "remote_calls_avoided": sum(1 for r in track1_rows if r.get("remote_call_avoided", True)),
        "tasks": tasks_out,
    }
    if extra:
        receipt["extra"] = extra
    return receipt


def write_track1(
    track1_rows: list[dict],
    out_dir: Path,
    extra: dict | None = None,
    no_receipts: bool = False,
) -> dict:
    """Écrit results.json (toujours) et receipts_internal.json (sauf --no-receipts).

    no_receipts=True : mode officiel hackathon AMD. results.json est alors la
    LISTE simple [{"task_id","answer"}] exigee par le harness — aucune metrique,
    aucun champ interne. receipts_internal.json n'est pas cree.

    no_receipts=False : mode audit local. results.json garde le format riche
    interne (format_version/total_tasks/tasks) + receipts complets.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = build_results(track1_rows)
    results_path = out_dir / "results.json"
    official_payload = build_official_results(track1_rows) if no_receipts else results
    results_path.write_text(
        json.dumps(official_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    receipts_path = out_dir / "receipts_internal.json"
    if not no_receipts:
        receipts = build_receipts(track1_rows, extra)
        receipts_path.write_text(
            json.dumps(receipts, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return {
        "results_path": results_path,
        "receipts_path": receipts_path if not no_receipts else None,
        "total_tasks": results["total_tasks"],
        "route_accuracy": results["route_accuracy"],
        "tokens_used_total": results["tokens_used_total"],
        "remote_calls": results["remote_calls"],
    }


# ── Standalone entry point ────────────────────────────────────────────────────

def standalone_run(tasks_file: Path, out_dir: Path) -> int:
    """Lance le pipeline Track 1 de façon autonome, sans run_benchmark.py."""
    from app.adapters import fireworks
    from app.adapters.fireworks import estimate_tokens
    from app.cli import load_memory_index, run_one
    from app.metrics.collector import MetricsCollector
    from app.router.decision import DEFAULT_MODEL_LADDER

    tasks = [normalize_task(t) for t in
             json.loads(tasks_file.read_text(encoding="utf-8"))]
    memory_index = load_memory_index()
    metrics = MetricsCollector()
    ladder = fireworks.allowed_models() or DEFAULT_MODEL_LADDER

    track1_rows: list[dict] = []

    print(f"TRACK 1 OFFICIAL — {len(tasks)} tasks")
    for task in tasks:
        t0 = time.perf_counter()
        decision = run_one(task["request"], metrics, memory_index, ladder)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        ir = decision["ir"]
        rec = metrics.records[-1]
        ok = decision["route"] == task.get("expected_route", decision["route"])

        row = {
            "id": task["id"],
            "request": task["request"],
            "expected_route": task.get("expected_route"),
            "actual_route": decision["route"],
            "route_correct": ok,
            "gate_verdict": decision["gate"]["verdict"],
            "gate_matched": decision["gate"].get("matched"),
            "level": decision["level"],
            "model": decision["model"],
            "intent_type": ir["intent_type"],
            "target_layer": ir["target_layer"],
            "missing": ir.get("missing", []),
            "fireworks_tokens": rec["fireworks_tokens"],
            "remote_call_avoided": rec["remote_call_avoided"],
            "routing_latency_ms": latency_ms,
            "output": decision.get("output", ""),
            "memory_entry": decision.get("memory_entry"),
            "topic_name": decision.get("topic", {}).get("topic", "general"),
            "actual_model_used": decision.get("actual_model_used"),
            "selected_rung": rec.get("selected_rung"),
            "selection_reason": rec.get("selection_reason"),
            "raw_prompt_chars": rec.get("raw_prompt_chars"),
            "system_prompt_chars": rec.get("system_prompt_chars"),
        }
        track1_rows.append(row)

        mark = "OK " if ok else "FAIL"
        print(f"  [{mark}] {task['id']:<22} -> {decision['route']:<20} "
              f"tok={rec['fireworks_tokens']:<5} {latency_ms:.1f}ms")

    summary = metrics.summary()
    result = write_track1(track1_rows, out_dir, extra={"obsidia_summary": summary})

    print()
    print(f"results    → {result['results_path']}")
    print(f"receipts   → {result['receipts_path']}")
    print(f"accuracy   : {result['route_accuracy']:.0%} ({result['total_tasks']} tasks)")
    print(f"tokens used: {result['tokens_used_total']}")
    print(f"remote calls: {result['remote_calls']}/{result['total_tasks']}")
    return 0


if __name__ == "__main__":
    tasks_file = Path("benchmarks/tasks.json")
    if "--tasks-file" in sys.argv:
        tasks_file = Path(sys.argv[sys.argv.index("--tasks-file") + 1])
    out_dir = ROOT / "results"
    raise SystemExit(standalone_run(tasks_file, out_dir))
