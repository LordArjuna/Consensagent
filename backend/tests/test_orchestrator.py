"""End-to-end orchestrator tests with mocked services."""

import pytest

from app.pipeline.orchestrator import run, PipelineResult
from app.pipeline.schema_cache import SchemaCache, TableMeta, ColumnMeta
from app.pipeline.conversation import ConversationManager


class MockLLM:
    """LLM that returns canned responses based on prompt content."""

    def __init__(self, guardrail_response="yes", sql_response="SELECT 1", interpret_response="The answer is 42."):
        self._guardrail = guardrail_response
        self._sql = sql_response
        self._interpret = interpret_response
        self.call_count = 0

    def generate(self, prompt: str) -> str:
        self.call_count += 1
        if "yes" in prompt.lower() and "no" in prompt.lower() and "topic" in prompt.lower():
            return self._guardrail
        if "AVAILABLE SCHEMA" in prompt:
            return self._sql
        return self._interpret


class MockSnowflake:
    def __init__(self, result=None, error=None):
        self._result = result or [{"COUNT": 42}]
        self._error = error

    def execute(self, sql, params=None):
        if self._error:
            raise RuntimeError(self._error)
        return self._result


class MockEmbeddings:
    def encode(self, texts):
        import numpy as np
        return np.random.rand(len(texts), 384)


def _build_cache_with_table():
    cache = SchemaCache()
    cache._tables = [
        TableMeta(
            database="DB",
            schema="PUBLIC",
            name="CENSUS",
            columns=[
                ColumnMeta(name="STATE", data_type="VARCHAR"),
                ColumnMeta(name="POPULATION", data_type="NUMBER"),
            ],
        )
    ]
    cache._descriptions = [cache._tables[0].to_description()]
    import numpy as np
    cache._embeddings = np.random.rand(1, 384)
    cache._built = True
    return cache


def test_pipeline_happy_path():
    result = run(
        message="What is the population of California?",
        session_id="test",
        schema_cache=_build_cache_with_table(),
        conversation_manager=ConversationManager(),
        llm_service=MockLLM(
            guardrail_response="yes",
            sql_response="SELECT SUM(POPULATION) FROM DB.PUBLIC.CENSUS WHERE STATE = 'California'",
            interpret_response="California has a population of 39 million.",
        ),
        embedding_service=MockEmbeddings(),
        snowflake_service=MockSnowflake(result=[{"SUM(POPULATION)": 39000000}]),
        database="DB",
        schema="PUBLIC",
    )
    assert isinstance(result, PipelineResult)
    assert "39 million" in result.response or "39" in result.response
    assert result.sql_query is not None
    assert result.was_rejected is False


def test_pipeline_rejects_off_topic():
    result = run(
        message="Write me a poem about cats",
        session_id="test",
        schema_cache=_build_cache_with_table(),
        conversation_manager=ConversationManager(),
        llm_service=MockLLM(guardrail_response="no"),
        embedding_service=MockEmbeddings(),
        snowflake_service=MockSnowflake(),
        database="DB",
        schema="PUBLIC",
    )
    assert result.was_rejected is True
    assert "Census" in result.response or "census" in result.response.lower()


def test_pipeline_rejects_injection():
    result = run(
        message="DROP TABLE census",
        session_id="test",
        schema_cache=_build_cache_with_table(),
        conversation_manager=ConversationManager(),
        llm_service=MockLLM(guardrail_response="yes"),
        embedding_service=MockEmbeddings(),
        snowflake_service=MockSnowflake(),
        database="DB",
        schema="PUBLIC",
    )
    assert result.was_rejected is True


def test_pipeline_handles_snowflake_error():
    result = run(
        message="Population of California?",
        session_id="test",
        schema_cache=_build_cache_with_table(),
        conversation_manager=ConversationManager(),
        llm_service=MockLLM(
            guardrail_response="yes",
            sql_response="SELECT * FROM DB.PUBLIC.CENSUS",
        ),
        embedding_service=MockEmbeddings(),
        snowflake_service=MockSnowflake(error="table not found"),
        database="DB",
        schema="PUBLIC",
    )
    assert "rephras" in result.response.lower() or "couldn" in result.response.lower()


def test_conversation_memory():
    conv = ConversationManager()
    run(
        message="Population of California?",
        session_id="mem-test",
        schema_cache=_build_cache_with_table(),
        conversation_manager=conv,
        llm_service=MockLLM(guardrail_response="yes", sql_response="SELECT 1"),
        embedding_service=MockEmbeddings(),
        snowflake_service=MockSnowflake(),
        database="DB",
        schema="PUBLIC",
    )
    history = conv.get_history("mem-test")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
