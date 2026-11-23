"""Versioned operational metrics API route."""

from typing import Any

from fastapi import APIRouter, Depends, Request

from api.auth import enforce_rate_limit

router = APIRouter(prefix="/v1", tags=["metrics"])


@router.get("/metrics")
def metrics(
    request: Request,
    _: str = Depends(enforce_rate_limit),
) -> dict[str, Any]:
    """Return aggregate latency, caching, area, listing, and token metrics."""
    return request.app.state.monitoring.get_metrics()
