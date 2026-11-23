"""Tests for API authentication, routes, caching, errors, and metrics."""

from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

from agent.llm import LLMProviderError
from api.cache import TTLCache
from api.dependencies import get_agent, get_retriever
from api.main import create_app
from api.monitoring import MonitoringStore
from api.rate_limit import SlidingWindowRateLimiter
from data.schemas import (
    ChatRequest,
    ChatResponse,
    Listing,
    RetrievedItem,
)

API_KEY = "test-api-key"
HEADERS = {"X-API-Key": API_KEY}


class StubAgent:
    """Return a fixed response or raise a configured provider failure."""

    def __init__(
        self,
        response: Optional[ChatResponse] = None,
        error: Optional[Exception] = None,
    ) -> None:
        self.response = response or ChatResponse(
            reply="Sample response",
            latency_ms=1,
        )
        self.error = error
        self.calls = 0
        self.session_ids: list[str] = []

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.calls += 1
        self.session_ids.append(request.session_id)
        if self.error:
            raise self.error
        return self.response


class StubRetriever:
    """Return one sample listing and count actual retrieval calls."""

    def __init__(self) -> None:
        self.calls = 0
        self.queries: list[str] = []
        self.filters: list[Optional[dict[str, Any]]] = []

    def retrieve(
        self,
        query: str,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[RetrievedItem]:
        self.calls += 1
        self.queries.append(query)
        self.filters.append(filters)
        listing = Listing(
            id="NC-001",
            title="Sample Cairo Apartment",
            area="New Cairo",
            city="New Cairo",
            developer="Sample Developer",
            price=3_000_000,
            area_sqm=120,
            bedrooms=2,
            bathrooms=2,
            delivery_date="2028-03-31",
            down_payment_pct=10,
            installment_years=8,
            description="SAMPLE listing.",
            property_type="Apartment",
        )
        return [
            RetrievedItem(
                id=f"listing:{listing.id}",
                content=listing.description or "",
                source=f"data/raw/listings.csv#{listing.id}",
                kind="listing",
                score=0.9,
                listing=listing,
            )
        ]

    def get_listing(self, listing_id: str) -> Optional[Listing]:
        """Return deterministic comparison fixtures by identifier."""
        prices = {"NC-001": 3_000_000, "NC-002": 2_800_000, "NC-MISSING": None}
        if listing_id not in prices:
            return None
        return Listing(
            id=listing_id,
            title=f"Sample {listing_id}",
            area="New Cairo",
            city="New Cairo",
            developer="Sample Developer",
            price=prices[listing_id],
            area_sqm=120,
            bedrooms=2,
            bathrooms=2,
            delivery_date=None,
            down_payment_pct=10 if prices[listing_id] is not None else None,
            installment_years=8 if prices[listing_id] is not None else None,
            description="SAMPLE listing.",
            property_type="Apartment",
        )


@pytest.fixture
def api_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Create an isolated app backed by temporary metrics storage."""
    monkeypatch.setenv("API_KEY", API_KEY)
    app = create_app(
        monitoring=MonitoringStore(tmp_path / "metrics.sqlite"),
        response_cache=TTLCache(ttl_seconds=60),
        rate_limiter=SlidingWindowRateLimiter(max_requests=60, window_seconds=60),
    )
    return app


def test_health_is_public(api_app: Any) -> None:
    response = TestClient(api_app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_requires_api_key_and_returns_contract(api_app: Any) -> None:
    agent = StubAgent()
    api_app.dependency_overrides[get_agent] = lambda: agent
    client = TestClient(api_app)

    missing_key = client.post(
        "/v1/chat",
        json={"session_id": "s1", "message": "Hello", "language": "en"},
    )
    response = client.post(
        "/v1/chat",
        headers=HEADERS,
        json={"session_id": "s1", "message": "Hello", "language": "en"},
    )

    assert missing_key.status_code == 401
    assert missing_key.json()["error"]["code"] == "INVALID_API_KEY"
    assert response.status_code == 200
    assert response.json()["reply"] == "Sample response"
    assert agent.calls == 1
    assert agent.session_ids == ["s1"]


def test_chat_provider_outage_uses_structured_503(api_app: Any) -> None:
    api_app.dependency_overrides[get_agent] = lambda: StubAgent(
        error=LLMProviderError("upstream detail", status_code=503)
    )

    response = TestClient(api_app).post(
        "/v1/chat",
        headers=HEADERS,
        json={"session_id": "s1", "message": "Hello", "language": "en"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_UNAVAILABLE"
    assert "upstream detail" not in response.text


def test_listing_search_is_cached_and_metrics_are_recorded(api_app: Any) -> None:
    retriever = StubRetriever()
    api_app.dependency_overrides[get_retriever] = lambda: retriever
    client = TestClient(api_app)
    params = {"query": "apartments", "areas": "New Cairo"}

    first = client.get("/v1/listings", params=params, headers=HEADERS)
    second = client.get("/v1/listings", params=params, headers=HEADERS)
    metrics = client.get("/v1/metrics", headers=HEADERS).json()

    assert first.status_code == second.status_code == 200
    assert first.json()[0]["id"] == "NC-001"
    assert retriever.calls == 1
    assert metrics["cache_hits"] == 1
    assert metrics["cache_misses"] == 1
    assert metrics["cache_hit_rate"] == 0.5
    assert metrics["area_request_counts"] == [{"area": "New Cairo", "count": 2}]
    assert metrics["most_viewed_listings"] == [{"listing_id": "NC-001", "views": 2}]


def test_plan_comparison_uses_deterministic_listing_terms(api_app: Any) -> None:
    api_app.dependency_overrides[get_retriever] = lambda: StubRetriever()

    response = TestClient(api_app).post(
        "/v1/compare-plans",
        headers=HEADERS,
        json={"listing_ids": ["NC-001", "NC-002"]},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["lowest_total_cost"] == "option_2"
    assert result["side_by_side"][0]["plan"]["monthly_payment"] == 28125


def test_plan_comparison_reports_missing_terms(api_app: Any) -> None:
    api_app.dependency_overrides[get_retriever] = lambda: StubRetriever()

    response = TestClient(api_app).post(
        "/v1/compare-plans",
        headers=HEADERS,
        json={"listing_ids": ["NC-001", "NC-MISSING"]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PLAN_DATA_UNAVAILABLE"
    assert response.json()["error"]["details"][0]["missing_fields"] == [
        "price",
        "down_payment_pct",
        "installment_years",
    ]


def test_rate_limit_is_per_key_and_returns_retry_after(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("API_KEY", API_KEY)
    api_app = create_app(
        monitoring=MonitoringStore(tmp_path / "metrics.sqlite"),
        response_cache=TTLCache(ttl_seconds=60),
        rate_limiter=SlidingWindowRateLimiter(max_requests=1, window_seconds=60),
    )
    client = TestClient(api_app)

    first = client.get("/v1/metrics", headers=HEADERS)
    second = client.get("/v1/metrics", headers=HEADERS)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["Retry-After"]
    assert second.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_validation_errors_use_the_shared_error_shape(api_app: Any) -> None:
    response = TestClient(api_app).post(
        "/v1/chat",
        headers=HEADERS,
        json={"session_id": "s1", "message": "Hello", "language": "xx"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"]


def test_monitoring_records_provider_token_usage(tmp_path: Path) -> None:
    monitoring = MonitoringStore(tmp_path / "metrics.sqlite")
    monitoring.record_token_usage(prompt_tokens=21, completion_tokens=8)

    assert monitoring.get_metrics()["token_usage"] == {
        "prompt_tokens": 21,
        "completion_tokens": 8,
        "total_tokens": 29,
    }
