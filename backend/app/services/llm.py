import logging
from typing import Generator

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self):
        self._client = None
        self._model_name: str = ""
        self._configured = False

    def configure(self, settings) -> None:
        try:
            self._client = genai.Client(api_key=settings.gemini_api_key)
            self._model_name = settings.gemini_model
            self._configured = True
            logger.info(f"Gemini configured with model: {self._model_name}")
        except Exception as e:
            self._configured = False
            logger.error(f"Gemini configuration failed: {e}")

    def generate(self, prompt: str) -> str:
        if not self._client:
            raise RuntimeError("LLM not configured")

        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
        )
        return response.text

    def generate_stream(self, prompt: str) -> Generator[str, None, None]:
        if not self._client:
            raise RuntimeError("LLM not configured")

        for chunk in self._client.models.generate_content_stream(
            model=self._model_name,
            contents=prompt,
        ):
            if chunk.text:
                yield chunk.text

    def test_connection(self) -> bool:
        if not self._configured or not self._client:
            return False
        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents="Say 'ok'",
            )
            return bool(response.text)
        except Exception as e:
            logger.error(f"Gemini test failed: {e}")
            return False
