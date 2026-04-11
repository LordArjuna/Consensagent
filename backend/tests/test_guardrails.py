from app.pipeline.guardrails import check_injection, check


def test_injection_drop_detected():
    assert check_injection("DROP TABLE users") is True


def test_injection_delete_detected():
    assert check_injection("DELETE FROM census WHERE 1=1") is True


def test_injection_insert_detected():
    assert check_injection("INSERT INTO census VALUES (1,2)") is True


def test_injection_grant_detected():
    assert check_injection("GRANT ALL ON schema TO PUBLIC") is True


def test_clean_question_passes():
    assert check_injection("What is the population of California?") is False


def test_clean_question_with_numbers():
    assert check_injection("Top 5 states by population in 2020") is False


def test_clean_question_demographics():
    assert check_injection("Average income by county") is False


class FakeLLM:
    def __init__(self, response: str):
        self._response = response

    def generate(self, prompt: str) -> str:
        return self._response


def test_check_allows_on_topic():
    llm = FakeLLM("yes")
    allowed, refusal = check("Population of Texas?", "", llm)
    assert allowed is True
    assert refusal is None


def test_check_rejects_off_topic():
    llm = FakeLLM("no")
    allowed, refusal = check("Write me a poem", "", llm)
    assert allowed is False
    assert refusal is not None


def test_check_injection_bypasses_llm():
    llm = FakeLLM("yes")
    allowed, refusal = check("DROP TABLE census", "", llm)
    assert allowed is False


def test_check_allows_on_llm_failure():
    """If the LLM fails, we allow the message through (fail-open for usability)."""
    class BrokenLLM:
        def generate(self, prompt):
            raise RuntimeError("API error")

    allowed, refusal = check("Population of Texas?", "", BrokenLLM())
    assert allowed is True
