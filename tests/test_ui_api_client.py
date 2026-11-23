"""Tests that the Streamlit HTTP client uses the configured API contract."""

from typing import Any
from unittest.mock import Mock

import pytest

from ui.api_client import APIClientError, api_request


class StubResponse:
    """Provide the requests response fields used by the UI client."""

    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._payload = payload

    def json(self) -> Any:
        return self._payload


def test_api_request_uses_configured_url_and_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("API_KEY", "local-test-key")
    recorded: dict[str, Any] = {}

    def request(method: str, url: str, **kwargs: Any) -> StubResponse:
        recorded.update({"method": method, "url": url, **kwargs})
        return StubResponse(200, {"status": "ok"})

    monkeypatch.setattr("ui.api_client.requests.request", request)

    assert api_request("GET", "/health") == {"status": "ok"}
    assert recorded["url"] == "http://localhost:9000/health"
    assert recorded["headers"]["X-API-Key"] == "local-test-key"


def test_api_request_surfaces_structured_api_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ui.api_client.requests.request",
        Mock(
            return_value=StubResponse(
                422,
                {
                    "error": {
                        "code": "PLAN_DATA_UNAVAILABLE",
                        "message": "Required listing data is missing.",
                        "details": [{"listing_id": "NC-004"}],
                    }
                },
            )
        ),
    )

    with pytest.raises(APIClientError, match="PLAN_DATA_UNAVAILABLE") as error:
        api_request("POST", "/v1/compare-plans", json={"listing_ids": []})

    assert error.value.status_code == 422
    assert error.value.details == [{"listing_id": "NC-004"}]
