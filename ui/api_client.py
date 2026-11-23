"""HTTP-only client used by Streamlit pages to call the Aqarak API."""

import os
from typing import Any, Optional
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

load_dotenv()


class APIClientError(RuntimeError):
    """A safe, user-displayable API communication failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        details: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details or []


def api_request(
    method: str,
    path: str,
    *,
    params: Optional[dict[str, Any]] = None,
    json: Optional[dict[str, Any]] = None,
) -> Any:
    """Send an authenticated JSON request to the configured API service."""
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/") + "/"
    api_key = os.getenv("API_KEY", "").strip()
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    try:
        response = requests.request(
            method,
            urljoin(base_url, path.lstrip("/")),
            params=params,
            json=json,
            headers=headers,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise APIClientError(
            "Could not connect to the Aqarak API. Check that the API service is running."
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise APIClientError(
            "The Aqarak API returned an unreadable response.",
            status_code=response.status_code,
        ) from exc
    if not response.ok:
        raw_error = payload.get("error") if isinstance(payload, dict) else None
        error = raw_error if isinstance(raw_error, dict) else {}
        message = error.get("message", "The Aqarak API request failed.")
        code = error.get("code")
        if code:
            message = f"{message} ({code})"
        raise APIClientError(
            message,
            status_code=response.status_code,
            details=error.get("details") if isinstance(error, dict) else None,
        )
    return payload