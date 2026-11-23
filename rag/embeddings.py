"""Chroma's local default embedding function used for semantic retrieval."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def default_embedding_function() -> Any:
    """Return Chroma's bundled local embedding function.

    The embedding model is downloaded and cached by Chroma on first use.
    """
    try:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    except ImportError as exc:
        raise RuntimeError(
            "ChromaDB is required for vector embedding; install requirements.txt"
        ) from exc
    logger.info("Using Chroma's bundled local embedding function")
    return DefaultEmbeddingFunction()
