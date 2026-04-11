import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    success: bool
    rows: List[Dict[str, Any]] = field(default_factory=list)
    columns: List[str] = field(default_factory=list)
    error: Optional[str] = None
    is_empty: bool = False
    is_timeout: bool = False
    row_count: int = 0


def execute(sql: str, snowflake_service) -> ExecutionResult:
    """Execute a SQL query against Snowflake and return a structured result."""
    try:
        rows = snowflake_service.execute(sql)

        if not rows:
            return ExecutionResult(
                success=True,
                is_empty=True,
                row_count=0,
            )

        columns = list(rows[0].keys()) if rows else []
        return ExecutionResult(
            success=True,
            rows=rows,
            columns=columns,
            row_count=len(rows),
        )

    except Exception as e:
        error_str = str(e)
        is_timeout = "timeout" in error_str.lower() or "exceeded" in error_str.lower()

        if is_timeout:
            logger.warning(f"Executor: query timed out: {sql[:100]}")
        else:
            logger.error(f"Executor: query failed: {error_str}")

        return ExecutionResult(
            success=False,
            error=error_str,
            is_timeout=is_timeout,
        )


def format_results(result: ExecutionResult, max_rows: int = 20) -> str:
    """Format execution results as a markdown table for prompt inclusion."""
    if result.is_empty:
        return "(no results returned)"

    if not result.rows:
        return "(no data)"

    columns = result.columns
    rows = result.rows[:max_rows]

    header = " | ".join(columns)
    separator = " | ".join("---" for _ in columns)

    lines = [header, separator]
    for row in rows:
        line = " | ".join(str(row.get(c, "")) for c in columns)
        lines.append(line)

    table = "\n".join(lines)

    if result.row_count > max_rows:
        table += f"\n\n(Showing {max_rows} of {result.row_count} total rows)"

    return table
