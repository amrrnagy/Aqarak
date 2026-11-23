"""Small repeatable hit-rate evaluation for sample listing retrieval."""

import logging
from typing import Optional

from data.schemas import (
    RetrievalEvaluation,
    RetrievalEvaluationResult,
)
from rag.retriever import HybridRetriever

logger = logging.getLogger(__name__)

EVALUATION_QUERIES = (
    ("park view apartment near the business district", "NAC-001"),
    ("family townhouse near parks schools and a mosque", "NAC-004"),
    ("two bedroom home near university campuses and retail", "NC-002"),
    ("duplex with private garden beside clubhouse and pool", "OCT-003"),
    ("villa near golf course and international schools", "SZ-001"),
    ("beachfront chalet with lagoon marina and swimming pools", "NCST-001"),
    ("summer apartment near swimmable beach and family pools", "NCST-002"),
    ("quiet Sokhna cabin near marina and mountains", "AS-001"),
    ("compact studio for rental near universities", "NC-006"),
    ("large coastal family villa with private pool and beach paths", "NCST-004"),
)


def evaluate_retrieval(
    retriever: Optional[HybridRetriever] = None,
) -> RetrievalEvaluation:
    """Run ten sample queries and report whether each expected ID was retrieved."""
    active_retriever = retriever or HybridRetriever(top_k=20)
    results: list[RetrievalEvaluationResult] = []
    for query, expected_id in EVALUATION_QUERIES:
        retrieved = active_retriever.retrieve(query)
        found = any(
            item.listing is not None and item.listing.id == expected_id
            for item in retrieved
        )
        results.append(
            RetrievalEvaluationResult(
                query=query,
                expected_listing_id=expected_id,
                found=found,
            )
        )

    hit_count = sum(result.found for result in results)
    report = RetrievalEvaluation(
        query_count=len(results),
        hit_count=hit_count,
        hit_rate=hit_count / len(results),
        results=results,
    )
    logger.info(
        "Completed retrieval evaluation",
        extra={
            "query_count": report.query_count,
            "hit_count": report.hit_count,
            "hit_rate": report.hit_rate,
        },
    )
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    report = evaluate_retrieval()
    logger.info(
        "Retrieval hit rate: %.2f%% (%d/%d)",
        report.hit_rate * 100,
        report.hit_count,
        report.query_count,
        extra={
            "hit_count": report.hit_count,
            "query_count": report.query_count,
            "hit_rate_percent": round(report.hit_rate * 100, 2),
        },
    )
