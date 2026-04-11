import logging
from typing import List

import numpy as np

from app.pipeline.schema_cache import SchemaCache, TableMeta

logger = logging.getLogger(__name__)


def retrieve(
    question: str,
    schema_cache: SchemaCache,
    embedding_service,
    top_k: int = 5,
) -> List[TableMeta]:
    """
    Find the most relevant tables for a user question using embedding similarity.

    Falls back to returning all tables if embeddings aren't available.
    """
    all_tables = schema_cache.get_all_tables()
    cached_embeddings = schema_cache.get_embeddings()

    if not all_tables:
        logger.warning("Schema retrieval: no tables in cache")
        return []

    if cached_embeddings is None or not schema_cache.is_built:
        logger.warning("Schema retrieval: embeddings not available, returning all tables")
        return all_tables

    try:
        query_emb = embedding_service.encode([question])
        scores = np.dot(cached_embeddings, query_emb.T).flatten()

        ranked_indices = np.argsort(scores)[::-1]
        selected_indices = set(ranked_indices[:top_k].tolist())

        selected_tables = [all_tables[i] for i in sorted(selected_indices)]

        logger.info(
            f"Schema retrieval: selected {len(selected_tables)} tables: "
            f"{[t.name for t in selected_tables]}"
        )
        return selected_tables

    except Exception as e:
        logger.error(f"Schema retrieval failed: {e}, returning all tables")
        return all_tables


def format_schema(tables: List[TableMeta]) -> str:
    """Format selected tables as DDL strings for prompt inclusion."""
    if not tables:
        return "(no schema available)"
    return "\n".join(t.to_ddl() for t in tables)
