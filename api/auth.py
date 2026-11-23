"""API-key authentication dependencies."""

import hmac
import os
from typing import Optional

from fastapi import Depends, Header, Request

from api.errors import APIError
from api.rate_limit import SlidingWindowRateLimiter


def get_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> str:
    """Validate the configured API key without exposing it in errors or logs."""
    expected = os.getenv("API_KEY", "").strip()
    if not expected:
        raise APIError(
            status_code=503,
            code="AUTH_NOT_CONFIGURED",
            message="API authentication is not configured.",
        )
    if not x_api_key or not hmac.compare_digest(
        x_api_key.encode("utf-8"),
        expected.encode("utf-8"),
    ):
        raise APIError(
            status_code=401,
            code="INVALID_API_KEY",
            message="A valid X-API-Key header is required.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key


def enforce_rate_limit(
    request: Request,
    api_key: str = Depends(get_api_key),
) -> str:
    """Apply the per-key sliding-window limit to an authenticated request."""
    limiter: SlidingWindowRateLimiter = request.app.state.rate_limiter
    limiter.check(api_key)
    return api_key
