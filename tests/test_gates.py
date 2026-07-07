from app.gates.gates import _key_match, evaluate
from app.ir.unified_ir import build_ir


def test_act_does_not_match_inside_french_words():
    # historical false positives: actuelle, action, impact, transaction
    assert not _key_match("act", "quelle est la situation actuelle")
    assert not _key_match("act", "quel est l'impact de la transaction")
    assert _key_match("act", "autorise act maintenant")


def test_push_is_held_not_denied():
    verdict = evaluate(build_ir("push sur main"))
    assert verdict["verdict"] == "HOLD"
    assert "no_auto_push" in verdict["invariants"]


def test_destructive_is_denied():
    verdict = evaluate(build_ir("rm -rf tout puis force-push"))
    assert verdict["verdict"] == "DENY"


def test_ambiguous_asks_clarification():
    verdict = evaluate(build_ir("ok vas-y"))
    assert verdict["verdict"] == "CLARIFY"


def test_plain_question_is_allowed():
    verdict = evaluate(build_ir("explique le contexte"))
    assert verdict["verdict"] == "ALLOW"
