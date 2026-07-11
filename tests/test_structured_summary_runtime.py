from app.router.model_triage import (
    select_model_for_request,
    select_rung,
)
from benchmarks.track1_remote_answer_contract import (
    build_remote_answer_contract,
)


_MODELS = [
    "m/rung-zero",
    "m/rung-one",
    "m/rung-two",
]


def test_structured_summary_stays_on_rung_zero():
    prompt = (
        "Summarize the following text in exactly one sentence: "
        "Solar power is renewable but intermittent."
    )

    assert select_rung(
        prompt,
        answer_kind="structured_summary",
    ) == 0


def test_structured_summary_selects_first_allowed_model():
    prompt = (
        "Summarize this report in exactly two sentences: "
        "Demand increased while costs declined."
    )

    result = select_model_for_request(
        prompt,
        _MODELS,
        answer_kind="structured_summary",
    )

    assert result["selected_model"] == "m/rung-zero"
    assert result["selected_rung"] == 0


def test_structured_summary_contract_is_summary_specific():
    prompt = (
        "Summarize the following in exactly one sentence: "
        "Solar and wind power reduce emissions but require storage."
    )

    contract = build_remote_answer_contract(
        prompt,
        allowed_models=_MODELS,
    )

    text = contract["contract_prompt"].lower()

    assert contract["answer_kind"] == "structured_summary"
    assert contract["max_tokens"] == 420

    assert "return only the requested summary" in text
    assert "requested sentence count" in text

    assert "two well-known instances" not in text
    assert "use two well-known instances" not in text

    assert "do not add examples" in text
    assert "analysis" in text
    assert "planning" in text


def test_non_summary_triage_is_unchanged():
    assert select_rung(
        "Write a complete Python module implementing a cache.",
        answer_kind="code_file",
    ) != 0
