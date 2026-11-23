"""Structured API errors and FastAPI exception handlers."""

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class APIError(Exception):
    """An expected API failure with a stable code and safe client message."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: Optional[dict[str, str]] = None,
        details: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
        self.details = details


def _error_payload(
    code: str,
    message: str,
    details: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"error": error}


async def handle_api_error(_: Request, exc: APIError) -> JSONResponse:
    """Render a known API error using the shared JSON envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(exc.code, exc.message, exc.details),
        headers=exc.headers,
    )


async def handle_validation_error(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return safe field-level details for invalid request payloads."""
    details = [
        {
            "location": [str(part) for part in error["loc"]],
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            "VALIDATION_ERROR",
            "The request contains invalid or missing fields.",
            details,
        ),
    )


async def handle_http_error(
    _: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Normalize framework-generated 4xx responses."""
    messages = {
        404: "The requested resource was not found.",
        405: "The requested method is not allowed.",
    }
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(
            f"HTTP_{exc.status_code}",
            messages.get(exc.status_code, "The request could not be completed."),
        ),
        headers=exc.headers,
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected failures and return a non-sensitive fallback message."""
    logger.error(
        "Unhandled API request failure",
        extra={"path": request.url.path},
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content=_error_payload(
            "INTERNAL_ERROR",
            "An unexpected error occurred. Please try again later.",
        ),
    )


def install_exception_handlers(app: FastAPI) -> None:
    """Register stable handlers for expected and unexpected API errors."""
    app.add_exception_handler(APIError, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
