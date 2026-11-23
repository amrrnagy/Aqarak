"""Versioned property listing API routes."""

import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from agent.tools.search_listings import search_listings
from api.auth import enforce_rate_limit
from api.dependencies import get_retriever
from api.errors import APIError
from data.schemas import Listing
from rag.retriever import HybridRetriever

router = APIRouter(prefix="/v1", tags=["listings"])


@router.get("/listings", response_model=list[Listing])
def list_listings(
    request: Request,
    query: str = Query(min_length=1, max_length=500),
    areas: list[str] = Query(default=[]),
    city: Optional[str] = None,
    developer: Optional[str] = None,
    price_min: Optional[float] = Query(default=None, ge=0),
    price_max: Optional[float] = Query(default=None, ge=0),
    bedrooms: Optional[int] = Query(default=None, ge=0),
    delivery_by: Optional[date] = None,
    property_type: Optional[str] = None,
    limit: int = Query(default=10, ge=1, le=10),
    _: str = Depends(enforce_rate_limit),
    retriever: HybridRetriever = Depends(get_retriever),
) -> list[Listing]:
    """Apply structured filters before returning semantically ranked listings."""
    if price_min is not None and price_max is not None and price_min > price_max:
        raise APIError(
            status_code=422,
            code="INVALID_FILTER",
            message="price_min must not exceed price_max.",
        )

    filters: dict[str, object] = {}
    if areas:
        filters["areas"] = areas
    for key, value in (
        ("city", city),
        ("developer", developer),
        ("price_min", price_min),
        ("price_max", price_max),
        ("bedrooms", bedrooms),
        ("delivery_by", delivery_by.isoformat() if delivery_by else None),
        ("property_type", property_type),
    ):
        if value is not None:
            filters[key] = value

    cache_key = json.dumps(
        {"query": query, "filters": filters, "limit": limit},
        ensure_ascii=False,
        sort_keys=True,
    )
    cache_hit, cached = request.app.state.response_cache.get(cache_key)
    request.state.cache_hit = cache_hit
    if cache_hit:
        listings = cached
    else:
        try:
            items = search_listings(query, filters, retriever)
        except FileNotFoundError as exc:
            raise APIError(
                status_code=503,
                code="LISTINGS_NOT_INGESTED",
                message="The sample listing data is not available. Run data ingestion first.",
            ) from exc
        except ValueError as exc:
            raise APIError(
                status_code=422,
                code="INVALID_FILTER",
                message=str(exc),
            ) from exc
        listings = []
        seen: set[str] = set()
        for item in items:
            if item.listing is not None and item.listing.id not in seen:
                listings.append(item.listing)
                seen.add(item.listing.id)
            if len(listings) >= limit:
                break
        request.app.state.response_cache.set(cache_key, listings)

    request.state.areas = [listing.area for listing in listings if listing.area]
    request.state.listing_ids = [listing.id for listing in listings]
    return listings
