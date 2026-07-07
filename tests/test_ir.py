from app.ir.unified_ir import build_ir, normalize


def test_normalize_folds_accents_and_case():
    assert normalize("Résumé  de l'État") == "resume de l'etat"


def test_status_intent():
    ir = build_ir("statut du systeme")
    assert ir["intent_type"] == "status"
    assert ir["risk_level"] == "low"


def test_world_action_is_high_risk():
    ir = build_ir("push tout sur main")
    assert ir["intent_type"] == "world_action"
    assert ir["risk_level"] == "high"
    assert ir["needs"]["gate"]


def test_question_routes_to_brody_layer():
    ir = build_ir("explique le contexte")
    assert ir["intent_type"] == "question"
    assert ir["target_layer"] == "brody"


def test_unknown_reports_missing_intent():
    ir = build_ir("fais le truc")
    assert ir["intent_type"] == "unknown"
    assert "intent" in ir["missing"]


def test_constraints_always_present():
    for raw in ("statut", "push", "explique", "xyz"):
        ir = build_ir(raw)
        assert "no_auto_act" in ir["constraints"]
        assert "no_auto_commit" in ir["constraints"]
        assert "no_auto_push" in ir["constraints"]
