"""FastAPI application entry point and shared middleware configuration."""

import os
import time
import threading
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from api.cache import TTLCache
from api.errors import install_exception_handlers
from api.monitoring import MonitoringStore
from api.rate_limit import SlidingWindowRateLimiter
from api.routes import chat, compare, health, listings, metrics


def create_app(
    *,
    monitoring: Optional[MonitoringStore] = None,
    response_cache: Optional[TTLCache] = None,
    rate_limiter: Optional[SlidingWindowRateLimiter] = None,
) -> FastAPI:
    """Create an app instance with injectable infrastructure for tests."""
    load_dotenv()
    app = FastAPI(title="Aqarak API", version="1.0.0")
    app.state.monitoring = monitoring if monitoring is not None else MonitoringStore()
    app.state.response_cache = (
        response_cache if response_cache is not None else TTLCache()
    )
    app.state.rate_limiter = (
        rate_limiter if rate_limiter is not None else SlidingWindowRateLimiter()
    )
    app.state.agent = None
    app.state.retriever = None
    app.state.agent_lock = threading.Lock()
    app.state.retriever_lock = threading.Lock()

    origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:8501,http://127.0.0.1:8501",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
    )
    install_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(compare.router)
    app.include_router(listings.router)
    app.include_router(metrics.router)

    @app.middleware("http")
    async def record_api_metrics(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            path = request.url.path
            if path.startswith("/v1/") and path != "/v1/metrics":
                app.state.monitoring.record_request(
                    path=path,
                    status_code=status_code,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    cache_hit=getattr(request.state, "cache_hit", None),
                    areas=getattr(request.state, "areas", ()),
                    listing_ids=getattr(request.state, "listing_ids", ()),
                )

    return app


app = create_app()
