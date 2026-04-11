import logging
import re
from typing import List, Optional

from app.pipeline.schema_cache import TableMeta
from app.pipeline.schema_retrieval import format_schema
from app.pipeline.prompts import SYSTEM_PROMPT, SQL_GENERATION_PROMPT, get_few_shot_examples

logger = logging.getLogger(__name__)


def _extract_sql(raw_response: str) -> str:
    """Extract SQL from an LLM response, stripping markdown fences and commentary."""
    text = raw_response.strip()

    fence_match = re.search(r"```(?:sql)?\s*\n?(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()

    if text.upper().startswith("UNANSWERABLE"):
        return text

    lines = text.split("\n")
    sql_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith(("SELECT", "WITH", "FROM", "WHERE", "GROUP",
                                        "ORDER", "HAVING", "LIMIT", "JOIN", "LEFT",
                                        "RIGHT", "INNER", "OUTER", "UNION", "AND",
                                        "OR", "ON", "AS", "CASE", "(", ")")):
            sql_lines.append(line)
        elif sql_lines:
            sql_lines.append(line)

    if sql_lines:
        return "\n".join(sql_lines).strip()

    return text


def generate(
    question: str,
    tables: List[TableMeta],
    conversation_history: str,
    llm_service,
    database: str = "",
    schema: str = "",
    error_context: Optional[str] = None,
) -> str:
    """
    Generate a SQL query for the given question.

    Returns the SQL string, or a string starting with 'UNANSWERABLE:' if the
    question can't be answered.
    """
    schema_str = format_schema(tables)
    examples = get_few_shot_examples(database, schema)

    error_str = ""
    if error_context:
        error_str = (
            f"\nThe previous attempt failed with this error: {error_context}\n"
            f"Please fix the query to avoid this error."
        )

    prompt = SQL_GENERATION_PROMPT.format(
        system_prompt=SYSTEM_PROMPT,
        schema=schema_str,
        conversation_history=conversation_history or "(no prior conversation)",
        few_shot_examples=examples,
        question=question,
        error_context=error_str,
    )

    logger.info(f"SQL Generator: generating query for: {question[:100]}")
    raw = llm_service.generate(prompt)
    sql = _extract_sql(raw)
    logger.info(f"SQL Generator: produced: {sql[:200]}")
    return sql
