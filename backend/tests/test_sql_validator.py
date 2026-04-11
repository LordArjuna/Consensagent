import pytest

from app.pipeline.sql_validator import validate
from app.pipeline.schema_cache import SchemaCache


@pytest.fixture
def empty_cache():
    return SchemaCache()


def test_valid_select(empty_cache):
    sql = "SELECT state, population FROM census WHERE state = 'CA'"
    is_valid, error, cleaned = validate(sql, empty_cache)
    assert is_valid is True
    assert error is None
    assert "SELECT" in cleaned.upper()


def test_adds_limit(empty_cache):
    sql = "SELECT * FROM census"
    is_valid, error, cleaned = validate(sql, empty_cache)
    assert is_valid is True
    assert "LIMIT" in cleaned.upper()


def test_preserves_existing_limit(empty_cache):
    sql = "SELECT * FROM census LIMIT 10"
    is_valid, error, cleaned = validate(sql, empty_cache)
    assert is_valid is True
    assert "10" in cleaned


def test_rejects_drop(empty_cache):
    sql = "DROP TABLE census"
    is_valid, error, cleaned = validate(sql, empty_cache)
    assert is_valid is False
    assert "Blocked" in error or "blocked" in error.lower()


def test_rejects_delete(empty_cache):
    sql = "DELETE FROM census WHERE 1=1"
    is_valid, error, cleaned = validate(sql, empty_cache)
    assert is_valid is False


def test_rejects_insert(empty_cache):
    sql = "INSERT INTO census VALUES (1, 'CA', 39000000)"
    is_valid, error, cleaned = validate(sql, empty_cache)
    assert is_valid is False


def test_rejects_update(empty_cache):
    sql = "UPDATE census SET population = 0 WHERE state = 'CA'"
    is_valid, error, cleaned = validate(sql, empty_cache)
    assert is_valid is False


def test_rejects_empty(empty_cache):
    is_valid, error, cleaned = validate("", empty_cache)
    assert is_valid is False


def test_rejects_unanswerable(empty_cache):
    sql = "UNANSWERABLE: no table for weather data"
    is_valid, error, cleaned = validate(sql, empty_cache)
    assert is_valid is False
    assert "UNANSWERABLE" in error


def test_handles_with_clause(empty_cache):
    sql = "WITH cte AS (SELECT state FROM census) SELECT * FROM cte"
    is_valid, error, cleaned = validate(sql, empty_cache)
    assert is_valid is True


def test_handles_subquery(empty_cache):
    sql = "SELECT * FROM (SELECT state, SUM(pop) as total FROM census GROUP BY state) sub ORDER BY total DESC"
    is_valid, error, cleaned = validate(sql, empty_cache)
    assert is_valid is True
