"""Politique de plafond de capture baseline par modèle (LOT G2).

model_capture_ceiling_v1

Autorité unique pour le max_tokens envoyé lors des appels de capture
baseline (bras « classic agent » du benchmark live-baseline).

Séparation stricte des périmètres
----------------------------------
Ce module  : capture baseline uniquement (mesure de référence, sans
             objectif d'économie). Le modèle brut doit pouvoir terminer
             sa réponse sans troncature artificielle.

track1_remote_answer_contract._BUDGETS  : budgets courts Obsidia par
    answer_kind — jamais modifiés ici.

track1_response_profile._MAX_TOKENS     : profils de réponse bornés Obsidia —
    jamais modifiés ici.

Doctrine
--------
La baseline ne doit plus utiliser answer_kind pour déterminer max_tokens.
answer_kind reste une métadonnée de télémétrie uniquement.

Un modèle absent du registre provoque une erreur explicite avant tout
appel réseau : le plafond de capture doit être calibré et enregistré.

Smoke test de validation (LOT G2, 2026-07-11)
----------------------------------------------
  requested_max_tokens : 8192
  finish_reason        : stop
  completion_tokens    : 38
  truncated            : False
  error                : None
  Source               : appel direct à l'API Fireworks
"""
from __future__ import annotations

# ── Registre de plafond par modèle ───────────────────────────────────────────

BASELINE_MODEL_CAPTURE_POLICY: dict[str, dict] = {
    "accounts/fireworks/models/gpt-oss-120b": {
        "max_tokens":          8192,
        "policy_version":      "model_capture_ceiling_v1",
        "calibration_source":  "LOT_G1_lower_bound_plus_model_supported_ceiling",
    },
}


def baseline_capture_max_tokens(model_id: str) -> int:
    """Retourne le max_tokens de capture baseline pour model_id.

    Le plafond est propre au modèle — pas à l'answer_kind.

    Raises
    ------
    KeyError
        Si model_id est absent du registre. Le plafond de capture doit
        être calibré et enregistré avant tout appel réseau.
    """
    entry = BASELINE_MODEL_CAPTURE_POLICY.get(model_id)
    if entry is None:
        raise KeyError(
            f"Baseline capture ceiling not registered for model '{model_id}'. "
            "Calibrate the model's output ceiling and add it to "
            "BASELINE_MODEL_CAPTURE_POLICY in benchmarks/baseline_capture_policy.py "
            "before running live-baseline."
        )
    return int(entry["max_tokens"])


def capture_policy_metadata(model_id: str) -> dict:
    """Retourne les métadonnées de politique pour model_id (télémétrie).

    Raises
    ------
    KeyError
        Si model_id est absent du registre.
    """
    entry = BASELINE_MODEL_CAPTURE_POLICY.get(model_id)
    if entry is None:
        raise KeyError(
            f"Baseline capture ceiling not registered for model '{model_id}'."
        )
    return {
        "capture_max_tokens":     entry["max_tokens"],
        "capture_policy_version": entry["policy_version"],
        "capture_limit_source":   entry["calibration_source"],
    }
