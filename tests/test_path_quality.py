from benchmarks.path_quality import quality_axes


def _fake_report():
    return {
        "route_accuracy": 1.0,
        "latency": {
            "avg_routing_ms_local": 0.1,
            "avg_fireworks_call_s": 1.0,
        },
        "dynamic": {
            "avg_decision_ms": 0.05,
            "decisions_per_second": 20000,
        },
        "tasks": [
            {
                "id": "status",
                "expected_route": "no_model_needed",
                "actual_route": "no_model_needed",
                "route_correct": True,
                "level": 0,
                "model": None,
                "gate": "ALLOW",
                "intent_type": "status",
                "fireworks_tokens": 0,
                "routing_latency_s": 0.0001,
            },
            {
                "id": "hold",
                "expected_route": "hold_commands_only",
                "actual_route": "hold_commands_only",
                "route_correct": True,
                "level": 0,
                "model": None,
                "gate": "HOLD",
                "intent_type": "world_action",
                "fireworks_tokens": 0,
                "routing_latency_s": 0.0002,
            },
            {
                "id": "brody",
                "expected_route": "brody",
                "actual_route": "brody",
                "route_correct": True,
                "level": 1,
                "model": None,
                "gate": "ALLOW",
                "intent_type": "question",
                "fireworks_tokens": 0,
                "routing_latency_s": 0.0003,
            },
            {
                "id": "remote",
                "expected_route": "fireworks",
                "actual_route": "fireworks",
                "route_correct": True,
                "level": 3,
                "model": "accounts/fireworks/models/gpt-oss-120b",
                "gate": "ALLOW",
                "intent_type": "reasoning",
                "fireworks_tokens": 100,
                "routing_latency_s": 1.5,
            },
        ],
    }


def test_route_quality_uses_actual_route():
    q = quality_axes(_fake_report())
    assert q["route_quality"]["route_matches"] == 4
    assert q["route_quality"]["route_correct_true"] == 4


def test_no_model_leaks_on_level0_or_world_actions():
    q = quality_axes(_fake_report())
    assert q["path_quality"]["level0_model_leaks"] == 0
    assert q["path_quality"]["world_action_model_leaks"] == 0


def test_escalation_quality_is_separate_axis():
    q = quality_axes(_fake_report())
    assert q["escalation_quality"]["fireworks_expected"] == 1
    assert q["escalation_quality"]["fireworks_actual"] == 1
    assert q["escalation_quality"]["unnecessary_fireworks_calls"] == 0
    assert q["escalation_quality"]["tokens_off_fireworks_rows"] == 0


def test_speed_profile_by_level_and_route():
    q = quality_axes(_fake_report())
    assert q["speed_profile"]["by_level_ms"]["0"]["n"] == 2
    assert q["speed_profile"]["by_route_ms"]["fireworks"]["n"] == 1
    assert q["speed_profile"]["remote_local_latency_ratio"] == 10000.0


def test_no_global_quality_score_created():
    q = quality_axes(_fake_report())
    dumped_keys = set(q.keys())
    assert "quality_score" not in dumped_keys
    assert "score" not in dumped_keys
