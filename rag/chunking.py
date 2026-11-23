"""Paragraph-aware text chunking for retrieval documents."""

import logging

logger = logging.getLogger(__name__)


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 120) -> list[str]:
    """Split text into bounded overlapping chunks without dropping characters."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    normalized = "\n\n".join(
        paragraph.strip() for paragraph in text.splitlines() if paragraph.strip()
    )
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind("\n\n", start, end)
            if boundary > start:
                end = boundary
        chunks.append(normalized[start:end].strip())
        if end == len(normalized):
            break
        start = max(start + 1, end - overlap)
    logger.debug(
        "Split document into chunks",
        extra={"character_count": len(normalized), "chunk_count": len(chunks)},
    )
    return chunks
