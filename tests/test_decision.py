from app.router.decision import decide

MEMORY = {"CURRENT_STATE": "state entry", "PROOF_QUERY": "proof entry"}


def test_status_never_calls_a_model():
    d = decide("statut du systeme")
    assert d["level"] == 0
    assert d["route"] == "no_model_needed"
    assert d["model"] is None


def test_world_action_is_held_before_any_token():
    d = decide("execute ce script en production")
    assert d["level"] == 0
    assert d["route"] == "hold_commands_only"


def test_memory_beats_generation_on_canonical_topic():
    d = decide("ou on en est, recap", memory_index=MEMORY)
    assert d["route"] == "memory_hit"
    assert d["level"] == 2


def test_simple_question_goes_to_local_organ_or_local_solver():
    # Short vague contextual prompts are now closed by brody_readonly_local
    # (0 token) before the brody route is reached.
    d = decide("explique le contexte de cette decision")
    assert d["route"] in {"brody", "local_solver"}
    assert d["level"] <= 3


def test_reasoning_escalates_to_cheapest_sufficient_model():
    ladder = ["cheap", "mid", "big"]
    d = decide("analyse et compare ces deux algorithmes", model_ladder=ladder)
    assert d["route"] == "fireworks"
    assert d["model"] in ladder


def test_long_complex_request_climbs_the_ladder():
    ladder = ["cheap", "mid", "big"]
    short = decide("compare a et b", model_ladder=ladder)
    long_req = decide("implemente " + "un module complexe " * 40 + "dans le fichier core.py",
                      model_ladder=ladder)
    assert ladder.index(long_req["model"]) >= ladder.index(short["model"])
