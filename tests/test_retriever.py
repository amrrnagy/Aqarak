"""Tests for SQL-first hybrid retrieval and sample-source ingestion."""

import csv
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from data.schemas import RetrievedItem
from rag.evaluate import evaluate_retrieval
from rag.ingest import ingest_data
from rag.retriever import HybridRetriever


class MemoryVectorStore:
    """Small deterministic vector-store substitute for retrieval unit tests."""

    def __init__(self) -> None:
        self.records: dict[str, tuple[str, Mapping[str, Any]]] = {}
        self.last_listing_filter: set[str] = set()

    def upsert(
        self,
        ids: Sequence[str],
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, Any]],
    ) -> None:
        for document_id, document, metadata in zip(ids, documents, metadatas):
            self.records[document_id] = (document, metadata)

    def query(
        self,
        query_text: str,
        n_results: int,
        where: Optional[Mapping[str, Any]] = None,
    ) -> list[RetrievedItem]:
        kind = ""
        listing_ids: Optional[set[str]] = None
        if where and "$and" in where:
            conditions = where["$and"]
            kind = conditions[0]["kind"]["$eq"]
            listing_ids = set(conditions[1]["listing_id"]["$in"])
            self.last_listing_filter = listing_ids
        elif where:
            kind = where["kind"]["$in"][0]

        query_tokens = set(query_text.lower().split())
        ranked: list[tuple[float, RetrievedItem]] = []
        for document_id, (content, metadata) in self.records.items():
            if metadata["kind"] != kind:
                continue
            listing_id = metadata.get("listing_id")
            if listing_ids is not None and listing_id not in listing_ids:
                continue
            content_tokens = set(content.lower().split())
            score = len(query_tokens & content_tokens) / max(len(query_tokens), 1)
            ranked.append(
                (
                    score,
                    RetrievedItem(
                        id=document_id,
                        content=content,
                        source=str(metadata["source"]),
                        kind=kind,
                        score=score,
                    ),
                )
            )
        ranked.sort(key=lambda result: result[0], reverse=True)
        return [item for _, item in ranked[:n_results]]


def test_ingestion_and_retrieval_apply_sql_filters_before_semantic_search(
    tmp_path: Path,
) -> None:
    store = MemoryVectorStore()
    database = tmp_path / "listings.db"
    summary = ingest_data(db_path=database, vector_store=store)
    retriever = HybridRetriever(database, store, top_k=20)

    assert summary.valid_listings == 40
    assert summary.invalid_listings == 0
    assert summary.knowledge_chunks >= 15
    results = retriever.retrieve(
        "two bedroom apartment close to university",
        {"area": "New Cairo", "price_max": 5_000_000},
    )

    listing_results = [item for item in results if item.listing is not None]
    assert listing_results
    assert all(item.listing.area == "New Cairo" for item in listing_results)
    assert all(item.listing.price is not None for item in listing_results)
    assert all(item.listing.price <= 5_000_000 for item in listing_results)
    assert store.last_listing_filter == {"NC-001", "NC-002", "NC-004", "NC-006"}
    assert all(item.source for item in results)
    assert any(item.kind == "area_guide" for item in results)


def test_sample_missing_values_remain_missing_and_evaluation_runs_ten_queries(
    tmp_path: Path,
) -> None:
    store = MemoryVectorStore()
    database = tmp_path / "listings.db"
    ingest_data(db_path=database, vector_store=store)
    retriever = HybridRetriever(database, store, top_k=20)

    results = retriever.retrieve("East Axis Garden Duplex")
    matching = [item.listing for item in results if item.listing and item.listing.id == "NAC-003"]
    assert matching
    assert matching[0].price is None

    report = evaluate_retrieval(retriever)
    assert report.query_count == 10
    assert len(report.results) == 10
    assert 0 <= report.hit_rate <= 1


def test_ingestion_logs_and_skips_invalid_listing_rows(tmp_path: Path) -> None:
    source = tmp_path / "listings.csv"
    fields = [
        "id",
        "title",
        "area",
        "city",
        "developer",
        "price",
        "area_sqm",
        "bedrooms",
        "bathrooms",
        "delivery_date",
        "down_payment_pct",
        "installment_years",
        "description",
        "property_type",
    ]
    with source.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerow({"id": "VALID-1", "title": "Sample home", "price": "100"})
        writer.writerow({"id": "INVALID-1", "price": "not-a-number"})

    store = MemoryVectorStore()
    result = ingest_data(
        listings_csv=source,
        area_guides_dir=tmp_path / "empty-guides",
        developers_dir=tmp_path / "empty-developers",
        db_path=tmp_path / "listings.db",
        vector_store=store,
    )

    assert result.valid_listings == 1
    assert result.invalid_listings == 1
    assert "listing:VALID-1" in store.records
    assert "listing:INVALID-1" not in store.records
