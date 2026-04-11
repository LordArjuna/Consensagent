import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.pipeline import guardrails, schema_retrieval, sql_generator, sql_validator, executor, interpreter
from app.pipeline.conversation import ConversationManager
from app.pipeline.schema_cache import SchemaCache
from app.pipeline.prompts import TIMEOUT_MESSAGE, UNRECOVERABLE_MESSAGE

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


@dataclass
class PipelineResult:
    response: str
    sql_query: Optional[str] = None
    tables_used: List[str] = field(default_factory=list)
    was_rejected: bool = False
    attempts: int = 0


def run(
    message: str,
    session_id: str,
    schema_cache: SchemaCache,
    conversation_manager: ConversationManager,
    llm_service,
    embedding_service,
    snowflake_service,
    database: str = "",
    schema: str = "",
) -> PipelineResult:
    """
    Execute the full text-to-SQL pipeline:
    guardrails -> schema retrieval -> SQL generation -> validation -> execution -> interpretation.
    """
    history_str = conversation_manager.format_history(session_id)

    # 1. Guardrails
    allowed, refusal = guardrails.check(message, history_str, llm_service)
    if not allowed:
        conversation_manager.add_message(session_id, "user", message)
        conversation_manager.add_message(session_id, "assistant", refusal)
        return PipelineResult(response=refusal, was_rejected=True)

    # 2. Schema retrieval
    tables = schema_retrieval.retrieve(message, schema_cache, embedding_service)
    table_names = [t.name for t in tables]

    # 3. Generate + validate + execute loop
    error_context = None
    result = None
    final_sql = None

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"Pipeline attempt {attempt}/{MAX_RETRIES} for: {message[:80]}")

        # Generate SQL
        try:
            sql = sql_generator.generate(
                question=message,
                tables=tables,
                conversation_history=history_str,
                llm_service=llm_service,
                database=database,
                schema=schema,
                error_context=error_context,
            )
        except Exception as e:
            logger.error(f"SQL generation failed on attempt {attempt}: {e}")
            error_context = str(e)
            continue

        if sql.upper().startswith("UNANSWERABLE"):
            reason = sql.split(":", 1)[1].strip() if ":" in sql else "unknown reason"
            response = (
                f"I'm not able to answer that question with the available Census data. "
                f"Reason: {reason}"
            )
            conversation_manager.add_message(session_id, "user", message)
            conversation_manager.add_message(session_id, "assistant", response)
            return PipelineResult(response=response, tables_used=table_names, attempts=attempt)

        # Validate SQL
        valid, error, cleaned_sql = sql_validator.validate(sql, schema_cache)
        if not valid:
            logger.warning(f"SQL validation failed on attempt {attempt}: {error}")
            error_context = f"SQL validation error: {error}"
            continue

        final_sql = cleaned_sql

        # Execute SQL
        result = executor.execute(cleaned_sql, snowflake_service)
        if result.success:
            break

        if result.is_timeout:
            conversation_manager.add_message(session_id, "user", message)
            conversation_manager.add_message(session_id, "assistant", TIMEOUT_MESSAGE)
            return PipelineResult(
                response=TIMEOUT_MESSAGE,
                sql_query=cleaned_sql,
                tables_used=table_names,
                attempts=attempt,
            )

        error_context = f"SQL execution error: {result.error}"
        logger.warning(f"SQL execution failed on attempt {attempt}: {result.error}")

    # 4. Interpret results or return failure
    if result and result.success:
        response = interpreter.interpret(message, final_sql, result, llm_service)
    else:
        response = UNRECOVERABLE_MESSAGE

    # 5. Save conversation
    conversation_manager.add_message(session_id, "user", message)
    conversation_manager.add_message(session_id, "assistant", response)

    return PipelineResult(
        response=response,
        sql_query=final_sql,
        tables_used=table_names,
        attempts=MAX_RETRIES if not (result and result.success) else attempt,
    )
