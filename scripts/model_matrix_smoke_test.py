"""Model matrix smoke test — compare Fireworks models on 3 Track1 contract categories.

Usage:
  python scripts/model_matrix_smoke_test.py [--dry-run] [--no-discover]
                                            [--quality-discovery]

  --dry-run           Skip live calls; show discovered models + contract design only.
  --no-discover       Skip GET /models; use DEFAULT_CANDIDATES only.
  --quality-discovery Use uncapped budgets to observe natural completion length.
                      Produces recommended_final_max_tokens per cell.

Modes:
  calibrated_budget_v1   (default)  comparison=280 / summary=380 / code=700
  quality_discovery_v1   (flag)     comparison=1200 / summary=1200 / code=2200

Environment:
  FIREWORKS_API_KEY   Required for live calls.
  FIREWORKS_BASE_URL  Default: https://api.fireworks.ai/inference/v1
  ALLOWED_MODELS      Optional override comma-separated list.

Output:
  results/model_matrix_report.json
  Console table: model | task | tokens | latency | meta | code_ok | lang | trunc | ok
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.adapters.fireworks import chat

# ── Default candidates (validated + configured in repo) ──────────────────────

DEFAULT_CANDIDATES = [
    "accounts/fireworks/models/gpt-oss-120b",
    "accounts/fireworks/models/deepseek-v4-pro",
    "accounts/fireworks/models/glm-5p2",
]

# glm-5p1 excluded: hardwired "Analyze the Request" template, language=EN regardless
# of instruction, code_only=FALSE on code_file. See model_matrix_report.json v0.
_EXCLUDED_MODELS = {
    "accounts/fireworks/models/glm-5p1": (
        "hardwired meta template / language failure / code_only failure"
    ),
}

# Families to search when discovering via GET /models
_DISCOVERY_FAMILIES = {
    "gpt-oss", "glm", "deepseek", "gemma", "qwen", "llama", "mistral",
}

# ── Budget profiles ───────────────────────────────────────────────────────────

_CALIBRATED_BUDGETS: dict[str, int] = {
    "comparison_missing_referent": 280,
    "structured_summary":          380,
    "code_file":                   700,
}

_QUALITY_DISCOVERY_BUDGETS: dict[str, int] = {
    "comparison_missing_referent": 1200,
    "structured_summary":          1200,
    "code_file":                   2200,
}

# ── Contract definitions — NOT hardcoded by task_id ──────────────────────────

_CONTRACTS: list[dict] = [
    {
        "contract_id":             "comparison_missing_referent",
        "answer_kind":             "comparison",
        "output_shape":            "compact_sections",
        "missing_referent":        True,
        "language":                "fr",
        "target_words":            150,
        "max_tokens":              280,
        "code_only":               False,
        "forbid_meta_reasoning":   True,
        "forbid_task_description": True,
        "forbid_planning":         True,
        "forbid_unrequested_tables": True,
        "request": (
            "analyse et compare ces deux strategies de cache distribue "
            "et derive la complexite de chacune"
        ),
    },
    {
        "contract_id":             "structured_summary",
        "answer_kind":             "structured_summary",
        "output_shape":            "compact_sections",
        "missing_referent":        False,
        "language":                "fr",
        "target_words":            180,
        "max_tokens":              380,
        "code_only":               False,
        "forbid_meta_reasoning":   True,
        "forbid_task_description": True,
        "forbid_planning":         True,
        "forbid_unrequested_tables": True,
        "request": (
            "resume de maniere structuree les tradeoffs consistency availability "
            "pour un systeme distribue multi region"
        ),
    },
    {
        "contract_id":             "code_file",
        "answer_kind":             "code_file",
        "output_shape":            "code_only",
        "missing_referent":        False,
        "language":                "fr",
        "target_words":            0,
        "max_tokens":              700,
        "code_only":               True,
        "forbid_meta_reasoning":   True,
        "forbid_task_description": True,
        "forbid_planning":         True,
        "forbid_unrequested_tables": True,
        "request": (
            "implemente en python une fonction de rate limiting token bucket "
            "avec tests dans le fichier limiter.py"
        ),
    },
]

# ── Contract prompt builder ───────────────────────────────────────────────────

def build_contract_prompt(c: dict) -> str:
    """Build a system prompt dynamically from contract fields. No task_id hardcoding."""
    parts: list[str] = []

    parts.append("Answer the request directly and concisely.")

    if c.get("forbid_task_description"):
        parts.append(
            "Do not start with 'The user asks', 'The user wants', "
            "'Understand the Goal', 'Analyze the Request', "
            "or any description of the request."
        )

    if c.get("forbid_meta_reasoning"):
        parts.append(
            "Do not include analysis steps, reasoning chains, "
            "planning, or preamble. Go straight to the answer."
        )

    if c.get("code_only"):
        parts.append(
            "Return only valid code. No explanation before or after the code. "
            "Do not use markdown code fences unless the request explicitly asks for them."
        )
    else:
        output_shape = c.get("output_shape", "prose")
        if output_shape == "compact_sections":
            tw = c.get("target_words", 180)
            parts.append(
                f"Structure the answer in at most 2-3 compact sections. "
                f"Target {tw} words total."
            )

    if c.get("missing_referent"):
        parts.append(
            "If no specific examples are given, use two common well-known instances "
            "and answer directly without mentioning that examples were missing."
        )

    if c.get("language") == "fr":
        parts.append("Answer in French.")
    elif c.get("language") == "en":
        parts.append("Answer in English.")

    if c.get("forbid_unrequested_tables"):
        parts.append("Avoid tables unless explicitly requested.")

    return " ".join(parts)

# ── Quality signal detectors ──────────────────────────────────────────────────

_META_REASONING_PATTERNS: list[str] = [
    r"(?i)^the user (asks?|wants?|is asking|needs?)",
    r"(?i)^understand(ing)? the (goal|request|task|problem)",
    r"(?i)^analyz(e|ing) the (request|task|problem)",
    r"(?i)^(first|step 1|step one)[,:\s]",
    r"(?i)^(let me|let's|i (will|would|should|need to))\b",
    r"(?i)^(we (need to|should|must|will|have to))\b",
    r"(?i)^to (answer|address|solve|tackle|respond to) (this|the)",
    r"(?i)^(the question asks?|the task (is|asks?|requires?))",
    r"(?i)^(goal|task|objective)[:\s]",
    r"(?i)^the instruction says?\b",
]

_META_BODY_PATTERNS: list[str] = [
    r"(?i)\bthe user (asks?|wants?|requested)\b",
    r"(?i)\bunderstand(ing)? the (goal|request)\b",
    r"(?i)\banalyz(e|ing) the (request|task|problem)\b",
    r"(?i)\bthe instruction says?\b",
    r"(?i)\bstep \d+[:\s]",
    r"(?i)\bmy approach\b",
    r"(?i)\blet me (first|begin|start)\b",
    r"(?i)\b(i need to|i should|we need to|we should) (choose|select|pick|identify|analyze|understand)\b",
]

_CODE_START_PATTERNS: list[str] = [
    r"^(import |from |def |class |#!|#!/)",
    r"^[a-zA-Z_][a-zA-Z0-9_]*\s*=",
    r"^(\"\"\"|\'\'\').*",
    r"^(TOKEN_BUCKET|class Token|def token|def rate)",
]

_FR_TOKENS: frozenset[str] = frozenset({
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "en",
    "dans", "pour", "avec", "sur", "par", "qui", "que", "est", "sont",
    "cette", "ces", "voici", "voila", "ainsi", "mais",
})


def starts_with_meta_reasoning(text: str) -> bool:
    """True if the first non-empty line matches a meta-reasoning pattern."""
    first = text.strip().split("\n")[0].strip() if text.strip() else ""
    return any(re.search(p, first) for p in _META_REASONING_PATTERNS)


def contains_meta_reasoning(text: str) -> bool:
    """True if any line in the answer matches a body meta-reasoning pattern."""
    if starts_with_meta_reasoning(text):
        return True
    return any(re.search(p, text) for p in _META_BODY_PATTERNS)


def code_only_respected(text: str, contract: dict) -> bool:
    """True if code_only contract is respected: starts with code, not analysis."""
    if not contract.get("code_only"):
        return True  # not applicable
    stripped = text.strip()
    if not stripped:
        return False
    # Strip optional markdown fence
    if stripped.startswith("```"):
        stripped = stripped.lstrip("`").split("\n", 1)[-1] if "\n" in stripped else ""
    first_line = stripped.split("\n")[0].strip()
    if any(re.match(p, first_line) for p in _CODE_START_PATTERNS):
        return True
    # Also accept if first non-empty line is a shebang or encoding comment
    if first_line.startswith("#"):
        return True
    return False


def language_respected(text: str, expected_lang: str) -> bool:
    """Heuristic: count FR tokens in first 60 words."""
    if not expected_lang or expected_lang == "unknown":
        return True
    words = re.findall(r"[a-zA-ZÀ-ÿ]+", text.lower())[:60]
    if expected_lang == "fr":
        fr_count = sum(1 for w in words if w in _FR_TOKENS)
        return fr_count >= 2
    if expected_lang == "en":
        en_tokens = {"the", "and", "of", "to", "in", "is", "that", "for", "with", "are"}
        en_count = sum(1 for w in words if w in en_tokens)
        return en_count >= 2
    return True


def table_unrequested_present(text: str, contract: dict) -> bool:
    """True if a markdown table appeared when it was forbidden."""
    if not contract.get("forbid_unrequested_tables"):
        return False
    return bool(re.search(r"\|.+\|", text))


def likely_truncated(result: dict) -> bool:
    """True if completion tokens hit ≥ 95% of max_tokens budget."""
    ct = result.get("completion_tokens", 0)
    mt = result.get("_max_tokens", 512)
    return ct > 0 and ct >= mt * 0.95


def cell_ok(row: dict) -> bool:
    """Overall quality: no meta, code respected, lang ok, not truncated, no error."""
    if row.get("error"):
        return False
    if row.get("starts_with_meta_reasoning"):
        return False
    if not row.get("code_only_respected", True):
        return False
    if not row.get("language_respected", True):
        return False
    if row.get("likely_truncated"):
        return False
    return True


def recommend_max_tokens(completion_tokens: int, truncated: bool) -> int | None:
    """Return recommended final max_tokens with 15% headroom, or None if still truncated."""
    if truncated or completion_tokens <= 0:
        return None
    return math.ceil(completion_tokens * 1.15)


def build_task_summary(rows: list[dict]) -> list[dict]:
    """Aggregate per-task statistics across models."""
    by_task: dict[str, list[dict]] = {}
    for r in rows:
        by_task.setdefault(r["contract_id"], []).append(r)

    summaries = []
    for contract_id, cell_rows in by_task.items():
        ok_rows = [r for r in cell_rows if r.get("ok")]
        non_trunc = [r for r in cell_rows if not r.get("likely_truncated") and not r.get("error")]

        best_quality   = min(ok_rows, key=lambda r: r.get("starts_with_meta_reasoning", 1),
                             default=None)
        fastest_ok     = min(ok_rows, key=lambda r: r.get("latency_s", 9999),
                             default=None)
        lowest_tok_ok  = min(ok_rows, key=lambda r: r.get("completion_tokens", 9999),
                             default=None)
        recommended    = best_quality or (min(non_trunc, key=lambda r: r.get("completion_tokens", 9999))
                                         if non_trunc else None)

        rec_tokens = None
        if recommended and not recommended.get("likely_truncated"):
            rec_tokens = recommend_max_tokens(
                recommended.get("completion_tokens", 0),
                recommended.get("likely_truncated", True),
            )

        summaries.append({
            "contract_id":          contract_id,
            "cells_total":          len(cell_rows),
            "cells_ok":             len(ok_rows),
            "best_model_by_quality": recommended["model_short"] if recommended else None,
            "fastest_ok_model":     fastest_ok["model_short"] if fastest_ok else None,
            "lowest_token_ok_model": lowest_tok_ok["model_short"] if lowest_tok_ok else None,
            "recommended_model":    recommended["model_short"] if recommended else None,
            "recommended_budget":   rec_tokens,
            "all_still_truncated":  all(r.get("likely_truncated") for r in cell_rows),
        })
    return summaries

# ── Model discovery via GET /models ──────────────────────────────────────────

def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "***"
    return key[:4] + "***" + key[-4:]


def discover_models(api_key: str, base_url: str) -> list[str]:
    """GET /models and filter by known family names. Returns full model IDs."""
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "obsidia-router/track1-benchmark",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"  [WARN] GET /models → HTTP {exc.code} — skipping discovery")
        return []
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  [WARN] GET /models → network error: {exc} — skipping discovery")
        return []

    models_raw = data if isinstance(data, list) else data.get("data", [])
    found: list[str] = []
    for entry in models_raw:
        model_id: str = entry if isinstance(entry, str) else entry.get("id", "")
        if not model_id:
            continue
        name_part = model_id.split("/")[-1].lower()
        if any(fam in name_part for fam in _DISCOVERY_FAMILIES):
            found.append(model_id)
    return sorted(set(found))


def build_candidate_list(
    api_key: str, base_url: str, no_discover: bool
) -> list[str]:
    """Merge DEFAULT_CANDIDATES with discovered models. Deduplicate."""
    candidates = list(DEFAULT_CANDIDATES)
    if not no_discover and api_key:
        print("  Discovering models via GET /models ...")
        discovered = discover_models(api_key, base_url)
        if discovered:
            print(f"  Found {len(discovered)} models from catalog:")
            for m in discovered:
                tag = "(already in default)" if m in candidates else "(NEW)"
                print(f"    {m.split('/')[-1]}  {tag}")
            for m in discovered:
                if m not in candidates:
                    candidates.append(m)
        else:
            print("  No catalog results — using DEFAULT_CANDIDATES only.")
    return candidates

# ── Core matrix runner ────────────────────────────────────────────────────────

def run_matrix(
    candidates: list[str],
    dry_run: bool = False,
    budget_override: dict[str, int] | None = None,
) -> list[dict]:
    """Run all (model × contract) cells. Returns flat list of result rows.

    budget_override: optional {contract_id: max_tokens} mapping; overrides
    _CONTRACTS[*]["max_tokens"] when provided (used for quality_discovery mode).
    """
    rows: list[dict] = []

    for model_id in candidates:
        short = model_id.split("/")[-1]
        for contract in _CONTRACTS:
            cid = contract["contract_id"]
            system_prompt = build_contract_prompt(contract)
            max_tok = (budget_override or {}).get(cid, contract["max_tokens"])
            request_text = contract["request"]

            t0 = time.perf_counter()
            result = chat(
                model_id,
                request_text,
                max_tokens=max_tok,
                system=system_prompt,
            )
            elapsed = round(time.perf_counter() - t0, 3)

            result["_max_tokens"] = max_tok  # needed for truncation check

            text = result.get("text", "")
            err = result.get("error")

            row: dict = {
                "model_id":    model_id,
                "model_short": short,
                "contract_id": cid,
                "dry_run":     result.get("dry_run", False),
                "error":       err,
                # Token accounting
                "prompt_tokens":     result.get("prompt_tokens", 0),
                "completion_tokens": result.get("completion_tokens", 0),
                "total_tokens":      result.get("total_tokens", 0),
                "max_tokens_budget": max_tok,
                "latency_s":         result.get("latency_s", elapsed),
                # Quality signals
                "starts_with_meta_reasoning": starts_with_meta_reasoning(text),
                "contains_meta_reasoning":    contains_meta_reasoning(text),
                "code_only_respected":        code_only_respected(text, contract),
                "language_respected":         language_respected(text, contract.get("language", "")),
                "table_unrequested_present":  table_unrequested_present(text, contract),
                "likely_truncated":           likely_truncated(result),
                "answer_preview":             text[:200].replace("\n", " "),
                # Contract metadata
                "answer_kind": contract["answer_kind"],
                "output_shape": contract["output_shape"],
                "system_prompt_used": system_prompt,
                "request": request_text,
            }
            row["ok"] = cell_ok(row)
            # Per-cell recommendation (meaningful only in quality_discovery mode)
            row["natural_completion_tokens"] = (
                row["completion_tokens"] if not row["likely_truncated"] else None
            )
            row["recommended_final_max_tokens"] = recommend_max_tokens(
                row["completion_tokens"], row["likely_truncated"]
            )
            row["recommendation_status"] = (
                "still_truncated" if row["likely_truncated"] else "ok"
            )
            rows.append(row)

    return rows

# ── Console table printer ─────────────────────────────────────────────────────

def _yn(val: bool | None) -> str:
    if val is None:
        return " - "
    return "YES" if val else " no"


def print_table(rows: list[dict]) -> None:
    print()
    hdr = (
        f"{'MODEL':<20} {'TASK':<30} {'TOK':>5} {'LAT':>6} "
        f"{'META':>5} {'CODE':>5} {'LANG':>5} {'TRUNC':>5} {'OK':>4}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        meta = _yn(r.get("starts_with_meta_reasoning"))
        code = _yn(None if r["answer_kind"] != "code_file" else r.get("code_only_respected"))
        lang = _yn(r.get("language_respected"))
        trunc = _yn(r.get("likely_truncated"))
        ok = " OK" if r.get("ok") else "FAIL"
        if r.get("error"):
            ok = " ERR"
        print(
            f"{r['model_short']:<20} {r['contract_id']:<30} "
            f"{r['total_tokens']:>5} {r['latency_s']:>6.2f} "
            f"{meta:>5} {code:>5} {lang:>5} {trunc:>5} {ok:>4}"
        )
    print()
    ok_count = sum(1 for r in rows if r.get("ok"))
    print(f"Result: {ok_count}/{len(rows)} cells OK")


def print_contract_design() -> None:
    """Show contract designs without running live calls."""
    print("\nContract design (--dry-run / no key):")
    for c in _CONTRACTS:
        prompt = build_contract_prompt(c)
        print(f"\n  [{c['contract_id']}]")
        print(f"    answer_kind  : {c['answer_kind']}")
        print(f"    max_tokens   : {c['max_tokens']}")
        print(f"    missing_ref  : {c['missing_referent']}")
        print(f"    system_prompt: {prompt[:120]}...")

# ── Report writer ─────────────────────────────────────────────────────────────

def write_report(
    rows: list[dict],
    out_path: Path,
    run_mode: str = "calibrated_budget_v1",
    budget_profile_used: dict[str, int] | None = None,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    task_summary = build_task_summary(rows)
    report = {
        "report_version":      "recalibrated_budgets_v1",
        "run_mode":            run_mode,
        "generated_at":        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "contracts_tested":    len(_CONTRACTS),
        "models_tested":       len({r["model_id"] for r in rows}),
        "cells_total":         len(rows),
        "cells_ok":            sum(1 for r in rows if r.get("ok")),
        "cells_still_truncated": sum(1 for r in rows if r.get("likely_truncated")),
        "budget_profile_used": budget_profile_used or {
            c["contract_id"]: c["max_tokens"] for c in _CONTRACTS
        },
        "excluded_models":     [
            {"model_id": mid, "reason": reason}
            for mid, reason in _EXCLUDED_MODELS.items()
        ],
        "gemma_status":        "unavailable_in_previous_catalog",
        "task_summary":        task_summary,
        "results":             rows,
    }
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nReport written → {out_path}")

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    dry_run_flag      = "--dry-run" in sys.argv
    no_discover       = "--no-discover" in sys.argv
    quality_discovery = "--quality-discovery" in sys.argv

    print("=" * 70)
    print("Obsidia Router — Model Matrix Smoke Test")
    print("=" * 70)

    # Spend guard: live mode runs N models x 3 categories with full
    # completions — the most expensive script in this repo. Explicit
    # CONFIRM_SPEND=1 is required for any live execution.
    if not dry_run_flag and os.environ.get("CONFIRM_SPEND", "").strip() != "1":
        print("REFUSED: live mode runs N models x 3 categories with full")
        print("completions and spends real Fireworks tokens.")
        print("Use --dry-run for the safe mode, or set CONFIRM_SPEND=1 to")
        print("explicitly authorize the spend.")
        return 2

    if quality_discovery:
        run_mode = "quality_discovery_v1"
        budget_override = _QUALITY_DISCOVERY_BUDGETS
        tok_upper = 2200
        print("  mode     : QUALITY DISCOVERY (uncapped budgets)")
    else:
        run_mode = "calibrated_budget_v1"
        budget_override = _CALIBRATED_BUDGETS
        tok_upper = 700
        print("  mode     : CALIBRATED BUDGET v1")

    api_key  = os.environ.get("FIREWORKS_API_KEY", "").strip()
    base_url = os.environ.get(
        "FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1"
    ).rstrip("/")

    if not api_key:
        print("SKIP: FIREWORKS_API_KEY not set.")
        print_contract_design()
        print("\nTo run live:")
        print(
            "  FIREWORKS_API_KEY=<key> "
            "python scripts/model_matrix_smoke_test.py [--quality-discovery]"
        )
        return 0

    masked = _mask_key(api_key)
    print(f"  key      : {masked}")
    print(f"  base_url : {base_url}")
    print(f"  contracts: {len(_CONTRACTS)}")

    candidates = build_candidate_list(api_key, base_url, no_discover)
    print(f"  models   : {len(candidates)}")
    for m in candidates:
        print(f"    {m.split('/')[-1]}")

    estimated_calls = len(candidates) * len(_CONTRACTS)
    print(f"\nEstimated Fireworks calls: {estimated_calls}")
    print(f"Estimated max tokens: ~{estimated_calls * tok_upper} (worst case upper bound)")

    if dry_run_flag:
        print("\n[DRY-RUN] Skipping live calls (--dry-run flag set).")
        print_contract_design()
        return 0

    print("\nRunning matrix ...\n")
    rows = run_matrix(candidates, budget_override=budget_override)

    print_table(rows)

    if quality_discovery:
        print("\n── Quality Discovery: natural completion tokens ──")
        for r in rows:
            rec = r.get("recommended_final_max_tokens")
            status = r.get("recommendation_status", "")
            nat = r.get("natural_completion_tokens")
            tag = f"→ recommend {rec}" if rec else f"→ {status}"
            print(
                f"  {r['model_short']:<20} {r['contract_id']:<30} "
                f"natural={nat!s:<6} {tag}"
            )

    out_path = ROOT / "results" / "model_matrix_report.json"
    write_report(rows, out_path, run_mode=run_mode, budget_profile_used=budget_override)

    return 0 if all(r.get("ok") or r.get("dry_run") for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
