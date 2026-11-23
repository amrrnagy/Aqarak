"""Shared lazily initialized runtime dependencies for API routes."""

from typing import Any, Mapping, Sequence

from fastapi import Request

from agent.agent import Agent
from agent.llm import (
    LLMClient,
    LLMConfigurationError,
    LLMResponse,
    create_llm_client,
)
from api.errors import APIError
from api.monitoring import MonitoringStore
from rag.retriever import HybridRetriever


class MonitoringLLMClient(LLMClient):
    """Record provider token usage while preserving the shared LLM interface."""

    def __init__(self, client: LLMClient, monitoring: MonitoringStore) -> None:
        self._client = client
        self._monitoring = monitoring

    def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] = (),
    ) -> LLMResponse:
        """Forward a completion and persist token usage when available."""
        response = self._client.chat(messages, tools)
        if response.usage is not None:
            self._monitoring.record_token_usage(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )
        return response


def get_agent(request: Request) -> Agent:
    """Lazily construct and reuse the configured assistant for this process."""
    with request.app.state.agent_lock:
        if request.app.state.agent is None:
            try:
                configured_client = create_llm_client()
            except LLMConfigurationError as exc:
                raise APIError(
                    status_code=503,
                    code="LLM_NOT_CONFIGURED",
                    message="The language model provider is not configured.",
                ) from exc
            llm_client = MonitoringLLMClient(
                configured_client,
                request.app.state.monitoring,
            )
            request.app.state.agent = Agent(llm_client=llm_client)
        return request.app.state.agent


def get_retriever(request: Request) -> HybridRetriever:
    """Lazily construct and reuse the local hybrid retriever."""
    with request.app.state.retriever_lock:
        if request.app.state.retriever is None:
            request.app.state.retriever = HybridRetriever()
        return request.app.state.retriever