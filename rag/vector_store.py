"""Persistent Chroma vector storage with a small provider-neutral interface."""

import logging
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Sequence

from data.schemas import RetrievedItem
from rag.embeddings import default_embedding_function

logger = logging.getLogger(__name__)


class VectorStore(Protocol):
    """Interface required by ingestion and hybrid retrieval."""

    def upsert(
        self,
        ids: Sequence[str],
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, Any]],
    ) -> None:
        """Insert or update document embeddings and metadata."""

    def query(
        self,
        query_text: str,
        n_results: int,
        where: Optional[Mapping[str, Any]] = None,
    ) -> list[RetrievedItem]:
        """Return semantically ranked documents matching metadata filters."""


class ChromaVectorStore:
    """Persistent vector store backed by one Chroma collection."""

    def __init__(
        self,
        persist_directory: Path | str,
        collection_name: str = "aqarak_knowledge",
    ) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError(
                "ChromaDB is required for vector storage; install requirements.txt"
            ) from exc

        self._client = chromadb.PersistentClient(path=str(persist_directory))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=default_embedding_function(),
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Initialized Chroma collection",
            extra={
                "persist_directory": str(persist_directory),
                "collection_name": collection_name,
            },
        )

    def upsert(
        self,
        ids: Sequence[str],
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, Any]],
    ) -> None:
        """Insert or update document embeddings and metadata."""
        if not ids:
            return
        self._collection.upsert(
            ids=list(ids),
            documents=list(documents),
            metadatas=[dict(metadata) for metadata in metadatas],
        )
        logger.info("Upserted vector documents", extra={"document_count": len(ids)})

    def query(
        self,
        query_text: str,
        n_results: int,
        where: Optional[Mapping[str, Any]] = None,
    ) -> list[RetrievedItem]:
        """Return semantically ranked documents matching metadata filters."""
        if n_results <= 0 or self._collection.count() == 0:
            return []
        arguments: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            arguments["where"] = dict(where)
        result = self._collection.query(**arguments)

        matches: list[RetrievedItem] = []
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for document_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances
        ):
            matches.append(
                RetrievedItem(
                    id=document_id,
                    content=document or "",
                    source=str(metadata.get("source", document_id)),
                    kind=metadata["kind"],
                    score=1.0 - float(distance),
                )
            )
        logger.debug(
            "Queried Chroma collection",
            extra={"result_count": len(matches), "requested_count": n_results},
        )
        return matches
