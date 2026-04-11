import logging
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        self._model: Optional[SentenceTransformer] = None
        self._loaded = False

    def load(self, settings) -> None:
        try:
            self._model = SentenceTransformer(settings.embedding_model_name)
            self._loaded = True
            logger.info(f"Embedding model loaded: {settings.embedding_model_name}")
        except Exception as e:
            self._loaded = False
            logger.error(f"Embedding model loading failed: {e}")

    def encode(self, texts: list[str]) -> np.ndarray:
        if not self._model:
            raise RuntimeError("Embedding model not loaded")
        return self._model.encode(texts, convert_to_numpy=True)

    def similarity(self, query: str, candidates: list[str]) -> list[tuple[int, float]]:
        """Return (index, score) pairs sorted by descending similarity."""
        if not self._model:
            raise RuntimeError("Embedding model not loaded")

        query_emb = self._model.encode([query], convert_to_numpy=True)
        cand_embs = self._model.encode(candidates, convert_to_numpy=True)

        scores = np.dot(cand_embs, query_emb.T).flatten()
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return ranked

    def test_connection(self) -> bool:
        if not self._loaded or not self._model:
            return False
        try:
            result = self.encode(["test"])
            return result.shape[0] == 1 and result.shape[1] > 0
        except Exception as e:
            logger.error(f"Embedding test failed: {e}")
            return False
