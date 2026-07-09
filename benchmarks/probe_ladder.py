"""Probe every rung of the model ladder with one minimal live call each.

Closes the "3rd rung never exercised" audit gap: proves each model in
ALLOWED_MODELS (or the default ladder) actually answers on this key.

Usage (spends a few tokens per rung):
    FIREWORKS_API_KEY=... python benchmarks/probe_ladder.py
    ALLOWED_MODELS="modelA,modelB" FIREWORKS_API_KEY=... python benchmarks/probe_ladder.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.adapters import fireworks
from app.router.decision import DEFAULT_MODEL_LADDER


def main() -> int:
    ladder = fireworks.allowed_models() or DEFAULT_MODEL_LADDER
    print(f"LADDER PROBE — {len(ladder)} rung(s)")
    failures = 0
    for i, model in enumerate(ladder):
        r = fireworks.chat(model, "Say OK", max_tokens=5)
        text = (r.get("text") or "")[:40].replace("\n", " ")
        tokens = r.get("total_tokens", 0)
        ok = not r.get("error") and "[dry-run]" not in text
        status = "LIVE_OK" if ok else ("DRY_RUN" if "[dry-run]" in text
                                       else f"FAIL {r.get('error', '')[:60]}")
        failures += 0 if ok else 1
        print(f"  rung {i}  {model.split('/')[-1]:<24} {status:<10} "
              f"tokens={tokens} text={text!r}")
    print(f"\nresult: {'ALL_RUNGS_LIVE' if failures == 0 else f'{failures} rung(s) not proven'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
