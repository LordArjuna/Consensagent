import logging

from app.pipeline.executor import ExecutionResult, format_results
from app.pipeline.prompts import INTERPRETATION_PROMPT, EMPTY_RESULT_MESSAGE

logger = logging.getLogger(__name__)


def interpret(
    question: str,
    sql: str,
    result: ExecutionResult,
    llm_service,
) -> str:
    """
    Synthesize a natural language answer from SQL execution results.

    Returns the final response string for the user.
    """
    if result.is_empty:
        return EMPTY_RESULT_MESSAGE

    results_str = format_results(result)

    prompt = INTERPRETATION_PROMPT.format(
        question=question,
        sql=sql,
        results=results_str,
    )

    try:
        response = llm_service.generate(prompt)
        return response.strip()
    except Exception as e:
        logger.error(f"Interpreter failed: {e}")
        return (
            f"I found {result.row_count} results but had trouble summarizing them. "
            f"Here are the raw results:\n\n{results_str}"
        )
