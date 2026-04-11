"""Integration tests for Gemini LLM connectivity.

Run with actual API key: pytest tests/test_llm.py -v
"""

import pytest

from app.config import get_settings
from app.services.llm import LLMService


@pytest.fixture
def llm():
    settings = get_settings()
    service = LLMService()
    service.configure(settings)
    return service


def test_connection(llm):
    assert llm.test_connection() is True


def test_generate(llm):
    response = llm.generate("What is 2 + 2? Reply with just the number.")
    assert "4" in response
