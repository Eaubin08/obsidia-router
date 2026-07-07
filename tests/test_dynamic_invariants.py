"""Dynamic bounded tests — the frame must hold on variations that were never
written down in advance.

A seeded generator composes request variations from template families; the
tests assert INVARIANTS, not fixed outputs:
  - world actions never reach a model (level 0, HOLD or DENY)
  - denied patterns are always denied, whatever the phrasing around them
  - every decision carries the no-auto invariants
  - level-3 escalation only happens with an ALLOW gate verdict
"""
import random

from app.router.decision import decide

SEED = 108
N_VARIATIONS = 60

_PREFIXES = ["", "peux tu ", "il faut ", "vite, ", "s'il te plait ", "bon alors "]
_SUFFIXES = ["", " maintenant", " sur le serveur", " des que possible", " ok ?"]

_WORLD_ACTIONS = ["push la branche", "commit les changements", "execute le script",
                  "deploy la version", "supprime les logs", "installe le package"]
_DENIED = ["rm -rf le dossier", "force-push sur main", "bypass gates"]
_QUESTIONS = ["explique le contexte", "pourquoi ce choix", "comment ca marche",
              "resume la situation"]
_REASONING = ["analyse les deux options et compare les couts",
              "genere un plan detaille de migration",
              "implemente la fonction de tri dans le fichier utils.py"]


def _variations(cores, rng):
    for _ in range(N_VARIATIONS):
        yield rng.choice(_PREFIXES) + rng.choice(cores) + rng.choice(_SUFFIXES)


def test_world_actions_never_reach_a_model():
    rng = random.Random(SEED)
    for raw in _variations(_WORLD_ACTIONS, rng):
        d = decide(raw)
        assert d["level"] == 0, raw
        assert d["route"] in {"hold_commands_only", "denied"}, raw
        assert d["model"] is None, raw


def test_denied_patterns_survive_rephrasing():
    rng = random.Random(SEED + 1)
    for raw in _variations(_DENIED, rng):
        assert decide(raw)["route"] == "denied", raw


def test_no_auto_invariants_present_on_every_decision():
    rng = random.Random(SEED + 2)
    for raw in _variations(_WORLD_ACTIONS + _QUESTIONS + _REASONING, rng):
        ir = decide(raw)["ir"]
        for inv in ("no_auto_act", "no_auto_commit", "no_auto_push"):
            assert inv in ir["constraints"], raw


def test_escalation_requires_allow_verdict():
    rng = random.Random(SEED + 3)
    for raw in _variations(_QUESTIONS + _REASONING + _WORLD_ACTIONS, rng):
        d = decide(raw)
        if d["route"] == "fireworks":
            assert d["gate"]["verdict"] == "ALLOW", raw
