from app.adapters.fireworks import extract_text


def test_standard_content_is_extracted():
    data = {"choices": [{"message": {"content": "hello"}}]}
    assert extract_text(data) == "hello"


def test_reasoning_model_without_content_does_not_crash():
    # gpt-oss style: content missing, reasoning_content present
    data = {"choices": [{"message": {"reasoning_content": "thinking..."}}]}
    assert extract_text(data) == "thinking..."


def test_null_content_falls_back():
    data = {"choices": [{"message": {"content": None}}]}
    assert extract_text(data) == "[empty completion]"


def test_missing_choices_returns_error_text():
    assert extract_text({}) == "[error] no choices in response"
    assert extract_text({"choices": []}) == "[error] no choices in response"
