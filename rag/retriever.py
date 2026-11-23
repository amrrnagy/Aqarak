"""Hybrid retrieval with exact SQLite filters followed by semantic ranking."""

import logging
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Optional

from data.schemas import Listing, RetrievedItem, UserPreferences
from rag.vector_store import ChromaVectorStore, VectorStore

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "processed" / "listings.db"
DEFAULT_VECTOR_PATH = ROOT / "data" / "processed" / "chroma"


class HybridRetriever:
    """Apply structured listing filters before semantic result retrieval."""

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
        vector_store: Optional[VectorStore] = None,
        top_k: int = 10,
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero")
        self._db_path = Path(db_path)
        self._vector_store = vector_store or ChromaVectorStore(DEFAULT_VECTOR_PATH)
        self._top_k = top_k

    @staticmethod
    def _normalize_filters(
        filters: Optional[Mapping[str, Any] | UserPreferences],
    ) -> dict[str, Any]:
        if filters is None:
            return {}
        if isinstance(filters, UserPreferences):
            values = filters.model_dump(mode="json", exclude_none=True)
        else:
            values = dict(filters)

        supported = {
            "budget_min",
            "budget_max",
            "price_min",
            "price_max",
            "price",
            "areas",
            "area",
            "city",
            "developer",
            "bedrooms",
            "delivery_by",
            "delivery_date",
            "property_type",
        }
        unknown = set(values) - supported
        if unknown:
            raise ValueError(f"Unsupported listing filters: {', '.join(sorted(unknown))}")
        return {key: value for key, value in values.items() if value is not None}

    def _filtered_listings(self, filters: dict[str, Any]) -> list[Listing]:
        if not self._db_path.is_file():
            raise FileNotFoundError(
                f"Listing database not found at {self._db_path}; run rag.ingest.ingest_data"
            )
        clauses: list[str] = []
        parameters: list[Any] = []

        for key in ("budget_min", "price_min"):
            if key in filters:
                clauses.append("price >= ?")
                parameters.append(filters[key])
        for key in ("budget_max", "price_max"):
            if key in filters:
                clauses.append("price <= ?")
                parameters.append(filters[key])
        if "price" in filters:
            clauses.append("price = ?")
            parameters.append(filters["price"])

        areas = filters.get("areas", filters.get("area"))
        if areas:
            area_values = list(areas) if isinstance(areas, (list, tuple, set)) else [areas]
            clauses.append(f"area IN ({', '.join('?' for _ in area_values)})")
            parameters.extend(area_values)
        for field in ("city", "developer", "bedrooms", "property_type"):
            if field in filters:
                clauses.append(f"{field} = ?")
                parameters.append(filters[field])

        delivery_by = filters.get("delivery_by")
        if delivery_by is not None:
            clauses.append("delivery_date <= ?")
            parameters.append(
                delivery_by.isoformat() if isinstance(delivery_by, date) else delivery_by
            )
        if filters.get("delivery_date") is not None:
            delivery_date = filters["delivery_date"]
            clauses.append("delivery_date = ?")
            parameters.append(
                delivery_date.isoformat()
                if isinstance(delivery_date, date)
                else delivery_date
            )

        query = "SELECT * FROM listings"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id"
        with sqlite3.connect(self._db_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, parameters).fetchall()
        return [Listing.model_validate(dict(row)) for row in rows]

    def get_listing(self, listing_id: str) -> Optional[Listing]:
        """Look up one listing by exact ID without semantic ranking."""
        if not listing_id.strip():
            raise ValueError("listing_id must not be empty")
        if not self._db_path.is_file():
            raise FileNotFoundError(
                f"Listing database not found at {self._db_path}; run rag.ingest.ingest_data"
            )
        with sqlite3.connect(self._db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM listings WHERE id = ?", (listing_id,)
            ).fetchone()
        return Listing.model_validate(dict(row)) if row is not None else None

    def retrieve(
        self,
        query: str,
        filters: Optional[Mapping[str, Any] | UserPreferences] = None,
    ) -> list[RetrievedItem]:
        """Filter listing candidates in SQL, then semantically rank documents."""
        if not query.strip():
            raise ValueError("query must not be empty")

        candidates = self._filtered_listings(self._normalize_filters(filters))
        listings_by_id = {listing.id: listing for listing in candidates}
        listing_matches: list[RetrievedItem] = []
        if listings_by_id:
            listing_matches = self._vector_store.query(
                query,
                min(self._top_k, len(listings_by_id)),
                where={
                    "$and": [
                        {"kind": {"$eq": "listing"}},
                        {"listing_id": {"$in": list(listings_by_id)}},
                    ]
                },
            )
            listing_matches = [
                RetrievedItem(
                    id=item.id,
                    content=item.content,
                    source=item.source,
                    kind="listing",
                    score=item.score,
                    listing=listings_by_id[item.id.removeprefix("listing:")]
                    if item.id.removeprefix("listing:") in listings_by_id
                    else listings_by_id.get(item.id),
                )
                for item in listing_matches
                if item.id.removeprefix("listing:") in listings_by_id
                or item.id in listings_by_id
            ]

        knowledge_matches = self._vector_store.query(
            query,
            self._top_k,
            where={"kind": {"$in": ["area_guide", "developer"]}},
        )
        results = listing_matches + knowledge_matches
        results.sort(
            key=lambda item: item.score if item.score is not None else float("-inf"),
            reverse=True,
        )
        logger.info(
            "Completed hybrid retrieval",
            extra={
                "query_length": len(query),
                "structured_listing_candidates": len(candidates),
                "returned_results": min(len(results), self._top_k),
            },
        )
        return results[: self._top_k]


def retrieve(
    query: str,
    filters: Optional[Mapping[str, Any] | UserPreferences] = None,
    retriever: Optional[HybridRetriever] = None,
) -> list[RetrievedItem]:
    """Convenience function using the default local database and Chroma store."""
    return (retriever or HybridRetriever()).retrieve(query, filters)
