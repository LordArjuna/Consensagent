import logging
from typing import Optional, Tuple

import sqlglot
from sqlglot import exp

from app.pipeline.schema_cache import SchemaCache

logger = logging.getLogger(__name__)

BLOCKED_OPERATIONS = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
    exp.Alter, exp.TruncateTable, exp.Merge,
)

MAX_LIMIT = 1000


def validate(
    sql: str,
    schema_cache: SchemaCache,
) -> Tuple[bool, Optional[str], str]:
    """
    Validate a generated SQL query.

    Returns:
        (is_valid, error_message, cleaned_sql)
    """
    if not sql or not sql.strip():
        return False, "Empty SQL query", ""

    if sql.upper().startswith("UNANSWERABLE"):
        return False, sql, ""

    try:
        parsed = sqlglot.parse(sql, read="snowflake")
    except sqlglot.errors.ParseError as e:
        return False, f"SQL syntax error: {e}", sql

    if not parsed or parsed[0] is None:
        return False, "Failed to parse SQL", sql

    statement = parsed[0]

    for blocked in BLOCKED_OPERATIONS:
        if isinstance(statement, blocked):
            return False, f"Blocked operation: {type(statement).__name__}. Only SELECT is allowed.", sql

    if not isinstance(statement, exp.Select):
        found_select = False
        for node in statement.walk():
            if isinstance(node, exp.Select):
                found_select = True
                break
        if not found_select:
            return False, "Only SELECT queries are allowed.", sql

    table_names = set()
    for table in statement.find_all(exp.Table):
        table_names.add(table.name.upper())

    if schema_cache.is_built:
        known_tables = {t.name.upper() for t in schema_cache.get_all_tables()}
        unknown = table_names - known_tables
        if unknown:
            logger.warning(f"SQL Validator: unknown tables referenced: {unknown}")

    cleaned = _ensure_limit(statement)

    return True, None, cleaned


def _ensure_limit(statement) -> str:
    """Add a LIMIT clause if the query doesn't have one."""
    has_limit = False
    for node in statement.walk():
        if isinstance(node, exp.Limit):
            has_limit = True
            break

    sql_str = statement.sql(dialect="snowflake")

    if not has_limit:
        sql_str = f"{sql_str} LIMIT {MAX_LIMIT}"

    return sql_str
