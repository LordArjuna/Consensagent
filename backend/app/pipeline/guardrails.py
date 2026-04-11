import logging
import re
from typing import Optional, Tuple

from app.pipeline.prompts import GUARDRAIL_PROMPT, REFUSAL_MESSAGE

logger = logging.getLogger(__name__)

DANGEROUS_PATTERNS = [
    re.compile(r"\b(DROP|DELETE|TRUNCATE|ALTER|CREATE|INSERT|UPDATE|MERGE)\b", re.IGNORECASE),
    re.compile(r"\b(GRANT|REVOKE|EXEC|EXECUTE)\b", re.IGNORECASE),
    re.compile(r"--\s*$", re.MULTILINE),
    re.compile(r";\s*(DROP|DELETE|INSERT|UPDATE)", re.IGNORECASE),
]


def check_injection(message: str) -> bool:
    """Return True if the message contains SQL injection patterns."""
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(message):
            return True
    return False


def check(
    message: str,
    conversation_history: str,
    llm_service,
) -> Tuple[bool, Optional[str]]:
    """
    Check whether a user message should be allowed through the pipeline.

    Returns:
        (is_allowed, refusal_message) -- if not allowed, refusal_message explains why.
    """
    if check_injection(message):
        logger.warning(f"Guardrails: SQL injection pattern detected")
        return False, "I can't process that request. Please ask a question about US Census data."

    try:
        prompt = GUARDRAIL_PROMPT.format(
            conversation_history=conversation_history or "(no prior conversation)",
            question=message,
        )
        response = llm_service.generate(prompt).strip().lower()

        if response.startswith("yes"):
            return True, None
        else:
            logger.info(f"Guardrails: off-topic question rejected")
            return False, REFUSAL_MESSAGE
    except Exception as e:
        logger.error(f"Guardrails LLM check failed: {e}, allowing through")
        return True, None
