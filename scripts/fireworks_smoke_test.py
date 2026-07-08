"""Fireworks smoke test — valide les appels HTTP sans révéler la clé API.

Usage:
  python scripts/fireworks_smoke_test.py

Teste chaque modèle validé avec un message minimal ("ping").
Affiche OK / FAIL avec code HTTP et extrait de réponse.
La clé API n'apparaît jamais dans la sortie.

Modèles validés sur ce compte:
  - accounts/fireworks/models/gpt-oss-120b
  - accounts/fireworks/models/glm-5p1

Modèles à exclure (404 sur ce compte):
  - accounts/fireworks/models/llama-v3p1-*
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.adapters.fireworks import chat, allowed_models

_VALIDATED_MODELS = [
    "accounts/fireworks/models/gpt-oss-120b",
    "accounts/fireworks/models/glm-5p1",
]

_SMOKE_PROMPT = "ping"


def _key_present() -> bool:
    return bool(os.environ.get("FIREWORKS_API_KEY", "").strip())


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "***"
    return key[:4] + "***" + key[-4:]


def run_smoke() -> int:
    print("=" * 60)
    print("Fireworks smoke test — obsidia-router/track1-benchmark")
    print("=" * 60)

    api_key = os.environ.get("FIREWORKS_API_KEY", "").strip()
    base = os.environ.get("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
    ladder = allowed_models() or _VALIDATED_MODELS

    if not api_key:
        print("SKIP: FIREWORKS_API_KEY not set — dry-run mode only")
        print()
        for model in ladder:
            result = chat(model, _SMOKE_PROMPT, max_tokens=16)
            status = "DRY-RUN" if result.get("dry_run") else "?"
            print(f"  [{status}] {model.split('/')[-1]}")
        return 0

    masked = _mask_key(api_key)
    print(f"  key     : {masked}")
    print(f"  base_url: {base}")
    print(f"  models  : {len(ladder)} to test")
    print()

    failures = 0
    for model in ladder:
        short = model.split("/")[-1]
        result = chat(model, _SMOKE_PROMPT, max_tokens=32)
        if result.get("error"):
            print(f"  [FAIL] {short}")
            # Never log Authorization; log error detail only
            err = result["error"]
            print(f"         error: {err}")
            failures += 1
        else:
            text_preview = (result.get("text") or "")[:80].replace("\n", " ")
            tokens = result.get("total_tokens", 0)
            latency = result.get("latency_s", 0.0)
            print(f"  [OK  ] {short}")
            print(f"         tokens={tokens}  latency={latency:.2f}s")
            print(f"         response: {text_preview!r}")

    print()
    if failures:
        print(f"RESULT: {failures}/{len(ladder)} FAILED")
        return 1
    print(f"RESULT: {len(ladder)}/{len(ladder)} OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_smoke())
