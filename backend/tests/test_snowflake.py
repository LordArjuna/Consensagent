"""Integration tests for Snowflake connectivity.

Run with actual credentials: pytest tests/test_snowflake.py -v
"""

import pytest

from app.config import get_settings
from app.services.snowflake import SnowflakeService


@pytest.fixture
def snowflake():
    settings = get_settings()
    service = SnowflakeService()
    service.connect(settings)
    yield service
    service.close()


def test_connection(snowflake):
    assert snowflake.test_connection() is True


def test_simple_query(snowflake):
    result = snowflake.execute("SELECT 1 AS num")
    assert len(result) == 1
    assert result[0]["NUM"] == 1
