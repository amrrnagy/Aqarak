"""Validate source listings and index structured and knowledge documents."""

import csv
import hashlib
import logging
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Optional

from pydantic import ValidationError

from data.schemas import IngestionSummary, Listing
from rag.chunking import chunk_text
from rag.vector_store import ChromaVectorStore, VectorStore

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
LISTING_COLUMNS = (
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
)


def _create_listing_table(connection: sqlite3.Connection) -> None:
    """Create the structured listing table when it does not yet exist."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS listings (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            area TEXT,
            city TEXT,
            developer TEXT,
            price REAL,
            area_sqm REAL,
            bedrooms INTEGER,
            bathrooms INTEGER,
            delivery_date TEXT,
            down_payment_pct REAL,
            installment_years REAL,
            description TEXT,
            property_type TEXT
        )
        """
    )


def _listing_document(listing: Listing) -> str:
    """Render a listing for semantic indexing without guessing missing data."""
    details = [
        f"Title: {listing.title}",
        f"Area: {listing.area or 'not provided'}",
        f"City: {listing.city or 'not provided'}",
        f"Developer: {listing.developer or 'not provided'}",
        f"Price EGP: {listing.price if listing.price is not None else 'not provided'}",
        f"Area square meters: {listing.area_sqm if listing.area_sqm is not None else 'not provided'}",
        f"Bedrooms: {listing.bedrooms if listing.bedrooms is not None else 'not provided'}",
        f"Bathrooms: {listing.bathrooms if listing.bathrooms is not None else 'not provided'}",
        f"Delivery date: {listing.delivery_date or 'not provided'}",
        f"Property type: {listing.property_type or 'not provided'}",
        f"Description: {listing.description or 'not provided'}",
    ]
    return "\n".join(details)


def _metadata(
    kind: str, source: str, extra: Optional[Mapping[str, Any]] = None
) -> dict[str, Any]:
    """Build Chroma-safe scalar metadata."""
    result: dict[str, Any] = {"kind": kind, "source": source}
    if extra:
        result.update(
            {key: value for key, value in extra.items() if value is not None}
        )
    return result


def _knowledge_documents(
    area_guides_dir: Path, developers_dir: Path
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Read and chunk area and developer markdown documents."""
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    for directory, kind in (
        (area_guides_dir, "area_guide"),
        (developers_dir, "developer"),
    ):
        for path in sorted(directory.glob("*.md")):
            try:
                source = path.relative_to(ROOT).as_posix()
            except ValueError:
                source = path.as_posix()
            text = path.read_text(encoding="utf-8")
            for index, chunk in enumerate(chunk_text(text)):
                digest = hashlib.sha256(
                    f"{source}:{index}:{chunk}".encode("utf-8")
                ).hexdigest()
                ids.append(f"doc:{digest}")
                documents.append(chunk)
                metadatas.append(_metadata(kind, source, {"chunk": index}))
    return ids, documents, metadatas


def ingest_data(
    listings_csv: Path | str = ROOT / "data" / "raw" / "listings.csv",
    area_guides_dir: Path | str = ROOT / "data" / "raw" / "area_guides",
    developers_dir: Path | str = ROOT / "data" / "raw" / "developers",
    db_path: Path | str = ROOT / "data" / "processed" / "listings.db",
    vector_store: Optional[VectorStore] = None,
) -> IngestionSummary:
    """Load valid CSV rows into SQLite and chunk source documents into Chroma."""
    csv_path = Path(listings_csv)
    guides_path = Path(area_guides_dir)
    developer_path = Path(developers_dir)
    database_path = Path(db_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if vector_store is None:
        vector_store = ChromaVectorStore(ROOT / "data" / "processed" / "chroma")

    valid_listings: list[Listing] = []
    invalid_count = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        with sqlite3.connect(database_path) as connection:
            _create_listing_table(connection)
            for row_number, raw_row in enumerate(reader, start=2):
                row = {
                    key: (value.strip() or None) if value is not None else None
                    for key, value in raw_row.items()
                    if key is not None
                }
                try:
                    listing = Listing.model_validate(row)
                except ValidationError as exc:
                    invalid_count += 1
                    logger.warning(
                        "Skipping invalid listing row",
                        extra={
                            "row_number": row_number,
                            "listing_id": row.get("id"),
                            "validation_errors": exc.errors(),
                        },
                    )
                    continue
                valid_listings.append(listing)
                values = listing.model_dump(mode="json")
                connection.execute(
                    f"""
                    INSERT INTO listings ({", ".join(LISTING_COLUMNS)})
                    VALUES ({", ".join("?" for _ in LISTING_COLUMNS)})
                    ON CONFLICT(id) DO UPDATE SET
                    {", ".join(f"{column}=excluded.{column}" for column in LISTING_COLUMNS if column != "id")}
                    """,
                    tuple(values[column] for column in LISTING_COLUMNS),
                )

    listing_ids = [f"listing:{listing.id}" for listing in valid_listings]
    listing_documents = [_listing_document(listing) for listing in valid_listings]
    listing_metadatas = [
        _metadata(
            "listing",
            f"data/raw/listings.csv#{listing.id}",
            {
                "listing_id": listing.id,
                "area": listing.area,
                "city": listing.city,
                "developer": listing.developer,
                "price": listing.price,
                "bedrooms": listing.bedrooms,
                "delivery_date": (
                    listing.delivery_date.isoformat()
                    if listing.delivery_date is not None
                    else None
                ),
                "property_type": listing.property_type,
            },
        )
        for listing in valid_listings
    ]
    doc_ids, doc_texts, doc_metadatas = _knowledge_documents(
        guides_path, developer_path
    )
    vector_store.upsert(
        listing_ids + doc_ids,
        listing_documents + doc_texts,
        listing_metadatas + doc_metadatas,
    )
    logger.info(
        "Ingested property and knowledge sources",
        extra={
            "valid_listings": len(valid_listings),
            "invalid_listings": invalid_count,
            "knowledge_chunks": len(doc_ids),
        },
    )
    return IngestionSummary(
        valid_listings=len(valid_listings),
        invalid_listings=invalid_count,
        knowledge_chunks=len(doc_ids),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    summary = ingest_data()
    logger.info(
        "Ingestion complete: %d valid listings, %d invalid listings, %d knowledge chunks",
        summary.valid_listings,
        summary.invalid_listings,
        summary.knowledge_chunks,
        extra={
            "valid_listings": summary.valid_listings,
            "invalid_listings": summary.invalid_listings,
            "knowledge_chunks": summary.knowledge_chunks,
        },
    )
