from app.router.model_triage import (
    select_model_for_request,
    select_rung,
)


_MODELS = [
    "model/rung-zero",
    "model/rung-one",
    "model/rung-two",
]


def test_simple_code_debugging_stays_on_rung_zero():
    prompt = """
Fix this Python function so it returns the average:

def average(numbers):
    total = 0
    for n in numbers:
        total += n
    return total
""".strip()

    assert select_rung(
        prompt,
        answer_kind="code_file",
    ) == 0


def test_simple_code_generation_stays_on_rung_zero():
    prompt = (
        "Write a Python function filter_even(numbers) that "
        "returns only the even integers."
    )

    result = select_model_for_request(
        prompt,
        _MODELS,
        answer_kind="code_file",
    )

    assert result["selected_rung"] == 0
    assert result["selected_model"] == "model/rung-zero"


def test_large_code_request_keeps_escalation_policy():
    prompt = (
        "Debug and redesign this Python implementation:\n"
        + ("value = transform(value)\n" * 100)
    )

    assert len(prompt) > 700

    assert select_rung(
        prompt,
        answer_kind="code_file",
    ) != 0


def test_structurally_complex_code_keeps_escalation_policy():
    prompt = (
        "Design a production asynchronous service with a "
        "database schema, authentication, Docker deployment, "
        "and multiple Python modules."
    )

    assert select_rung(
        prompt,
        answer_kind="code_file",
    ) != 0


def test_simple_code_policy_does_not_change_summary_policy():
    prompt = (
        "Summarize the following passage in two sentences."
    )

    assert select_rung(
        prompt,
        answer_kind="structured_summary",
    ) == 0
