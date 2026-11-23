"""Versioned chat API route."""

from fastapi import APIRouter, Depends, Request

from agent.agent import Agent, AgentExecutionError, ToolExecutionError
from agent.guardrails import NumericGuardrailError
from agent.llm import LLMConfigurationError, LLMProviderError
from agent.tools.installment_calc import InstallmentCalculationError
from api.auth import enforce_rate_limit
from api.dependencies import get_agent
from api.errors import APIError
from data.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    request: Request,
    _: str = Depends(enforce_rate_limit),
    agent: Agent = Depends(get_agent),
) -> ChatResponse:
    """Run one conversational turn without caching session-specific context."""
    try:
        response = agent.chat(payload)
    except LLMConfigurationError as exc:
        raise APIError(
            status_code=503,
            code="LLM_NOT_CONFIGURED",
            message="The language model provider is not configured.",
        ) from exc
    except LLMProviderError as exc:
        status_code = (
            503
            if exc.status_code in (429, 503)
            or (exc.status_code is not None and exc.status_code >= 500)
            else 502
        )
        message = (
            "The language model is temporarily unavailable. Please try again."
            if status_code == 503
            else "The language model provider could not complete the request."
        )
        raise APIError(
            status_code=status_code,
            code="LLM_UNAVAILABLE" if status_code == 503 else "LLM_REQUEST_FAILED",
            message=message,
        ) from exc
    except FileNotFoundError as exc:
        raise APIError(
            status_code=503,
            code="LISTINGS_NOT_INGESTED",
            message="The sample listing data is not available. Run data ingestion first.",
        ) from exc
    except (
        AgentExecutionError,
        ToolExecutionError,
        NumericGuardrailError,
        InstallmentCalculationError,
    ) as exc:
        raise APIError(
            status_code=502,
            code="AGENT_EXECUTION_FAILED",
            message="The assistant could not complete this request.",
        ) from exc

    request.state.areas = [
        listing.area for listing in response.listings if listing.area
    ]
    request.state.listing_ids = [listing.id for listing in response.listings]
    return response
