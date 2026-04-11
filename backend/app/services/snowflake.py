import logging
from typing import Any, Optional

import snowflake.connector

logger = logging.getLogger(__name__)


class SnowflakeService:
    def __init__(self):
        self._conn = None
        self._connected = False

    def connect(self, settings) -> None:
        try:
            self._conn = snowflake.connector.connect(
                account=settings.snowflake_account,
                user=settings.snowflake_user,
                password=settings.snowflake_password,
                database=settings.snowflake_database,
                schema=settings.snowflake_schema,
                warehouse=settings.snowflake_warehouse,
                login_timeout=30,
                network_timeout=30,
            )
            self._connected = True
            logger.info("Snowflake connection established")
        except Exception as e:
            self._connected = False
            logger.error(f"Snowflake connection failed: {e}")

    def execute(self, sql: str, params: Optional[tuple] = None) -> list[dict[str, Any]]:
        if not self._conn:
            raise RuntimeError("Snowflake not connected")

        cursor = self._conn.cursor()
        try:
            cursor.execute(sql, params)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            cursor.close()

    def test_connection(self) -> bool:
        if not self._connected or not self._conn:
            return False
        try:
            result = self.execute("SELECT CURRENT_VERSION() AS version")
            logger.info(f"Snowflake version: {result[0]['VERSION']}")
            return True
        except Exception as e:
            logger.error(f"Snowflake test failed: {e}")
            return False

    def close(self) -> None:
        if self._conn:
            try:
                self._conn.close()
                logger.info("Snowflake connection closed")
            except Exception:
                pass
            self._conn = None
            self._connected = False
