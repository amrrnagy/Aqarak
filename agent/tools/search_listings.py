"""Search listings and area knowledge through the hybrid retrieval layer."""

import logging
from typing import Any, Mapping, Optional

from data.schemas import RetrievedItem, UserPreferences
from rag.retriever import HybridRetriever

logger = logging.getLogger(__name__)


def search_listings(
    query: str,
    filters: Optional[Mapping[str, Any] | UserPreferences] = None,
    retriever: Optional[HybridRetriever] = None,
) -> list[RetrievedItem]:
    """Return attributed listing and knowledge matches for an assistant query."""
    active_retriever = retriever or HybridRetriever()
    results = active_retriever.retrieve(query, filters)
    logger.info(
        "Searched property listings",
        extra={"result_count": len(results), "query_length": len(query)},
    )
    return results
