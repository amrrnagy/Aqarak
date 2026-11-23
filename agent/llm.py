"""Provider-neutral language model contract with OpenAI and Gemini adapters."""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LLMToolCall(BaseModel):
    """A provider-independent tool name and decoded JSON arguments."""

    name: str
    arguments: dict[str, Any]


class LLMUsage(BaseModel):
    """Token counts returned by a provider when available."""

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


class LLMResponse(BaseModel):
    """Normalized content and tool calls returned by an LLM provider."""

    content: str = ""
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    usage: Optional[LLMUsage] = None


class LLMClient(ABC):
    """Abstract interface implemented by configured language model providers."""

    @abstractmethod
    def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] = (),
    ) -> LLMResponse:
        """Send a chat completion request and normalize its result."""


class LLMConfigurationError(RuntimeError):
    """Raised when provider configuration is incomplete or unsupported."""


class LLMResponseError(RuntimeError):
    """Raised when the provider returns a response that cannot be normalized."""


class LLMProviderError(RuntimeError):
    """Raised when a configured model provider rejects or cannot serve a request."""

    def __init__(
        self, message: str, *, status_code: Optional[int] = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenAIChatClient(LLMClient):
    """OpenAI-compatible Chat Completions adapter."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: Optional[str] = None,
        provider: str = "openai",
    ) -> None:
        if not api_key.strip():
            raise LLMConfigurationError("LLM_API_KEY must be configured")
        if not model.strip():
            raise LLMConfigurationError("LLM_MODEL must be configured")
        try:
            from openai import APIError, OpenAI
        except ImportError as exc:
            raise LLMConfigurationError(
                "OpenAI-compatible providers require the openai package"
            ) from exc
        client_options: dict[str, str] = {"api_key": api_key}
        if base_url is not None:
            client_options["base_url"] = base_url
        self._client = OpenAI(**client_options)
        self._model = model
        self._api_error = APIError
        self._provider = provider

    def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] = (),
    ) -> LLMResponse:
        """Call the configured compatible endpoint and normalize its response."""
        request: dict[str, Any] = {
            "model": self._model,
            "messages": [dict(message) for message in messages],
        }
        if tools:
            request["tools"] = [dict(tool) for tool in tools]
            request["tool_choice"] = "auto"
        try:
            response = self._client.chat.completions.create(**request)
        except self._api_error as exc:
            status_code = getattr(exc, "status_code", None)
            logger.warning(
                "LLM provider request failed",
                extra={"provider": self._provider, "status_code": status_code},
            )
            raise LLMProviderError(
                f"The {self._provider} provider could not complete the request.",
                status_code=status_code,
            ) from exc
        if not response.choices:
            raise LLMResponseError("LLM provider returned no completion choices")

        message = response.choices[0].message
        tool_calls: list[LLMToolCall] = []
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError as exc:
                raise LLMResponseError(
                    f"LLM returned invalid JSON for tool {call.function.name}"
                ) from exc
            if not isinstance(arguments, dict):
                raise LLMResponseError(
                    f"LLM arguments for tool {call.function.name} must be an object"
                )
            tool_calls.append(
                LLMToolCall(name=call.function.name, arguments=arguments)
            )

        provider_usage = response.usage
        usage = (
            LLMUsage(
                prompt_tokens=provider_usage.prompt_tokens,
                completion_tokens=provider_usage.completion_tokens,
            )
            if provider_usage is not None
            else None
        )
        normalized = LLMResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            usage=usage,
        )
        logger.info(
            "Received LLM completion",
            extra={
                "provider": self._provider,
                "model": self._model,
                "tool_call_count": len(tool_calls),
                "prompt_tokens": usage.prompt_tokens if usage else None,
                "completion_tokens": usage.completion_tokens if usage else None,
            },
        )
        return normalized


class GeminiChatClient(LLMClient):
    """Google GenAI adapter that normalizes Gemini function calls."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key.strip():
            raise LLMConfigurationError("LLM_API_KEY must be configured")
        if not model.strip():
            raise LLMConfigurationError("LLM_MODEL must be configured")
        try:
            from google import genai
            from google.genai import errors
            from google.genai import types
        except ImportError as exc:
            raise LLMConfigurationError(
                "The Gemini provider requires the google-genai package"
            ) from exc
        self._client = genai.Client(api_key=api_key)
        self._types = types
        self._model = model
        self._api_error = errors.APIError

    def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] = (),
    ) -> LLMResponse:
        """Call Gemini and normalize its text, function calls, and token counts."""
        system_instructions = [
            str(message["content"])
            for message in messages
            if message.get("role") == "system"
        ]
        contents = [
            self._types.Content(
                role="model" if message.get("role") == "assistant" else "user",
                parts=[self._types.Part(text=str(message.get("content", "")))],
            )
            for message in messages
            if message.get("role") != "system"
        ]
        config: dict[str, Any] = {}
        if system_instructions:
            config["system_instruction"] = "\n\n".join(system_instructions)
        if tools:
            declarations = []
            for tool in tools:
                function = tool.get("function")
                if not isinstance(function, Mapping):
                    raise LLMResponseError("Gemini tools must use function declarations")
                declarations.append(
                    self._types.FunctionDeclaration(
                        name=function["name"],
                        description=function.get("description"),
                        parametersJsonSchema=function.get("parameters", {}),
                    )
                )
            config["tools"] = [
                self._types.Tool(functionDeclarations=declarations)
            ]
            config["automatic_function_calling"] = (
                self._types.AutomaticFunctionCallingConfig(disable=True)
            )

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=self._types.GenerateContentConfig(**config),
            )
        except self._api_error as exc:
            status_code = getattr(exc, "code", None) or getattr(
                exc, "status_code", None
            )
            logger.warning(
                "LLM provider request failed",
                extra={"provider": "gemini", "status_code": status_code},
            )
            raise LLMProviderError(
                "The Gemini provider could not complete the request.",
                status_code=status_code,
            ) from exc
        if not response.candidates:
            raise LLMResponseError("Gemini returned no completion candidates")
        candidate = response.candidates[0]
        if candidate.content is None:
            raise LLMResponseError("Gemini completion did not contain message content")

        text_parts: list[str] = []
        tool_calls: list[LLMToolCall] = []
        for part in candidate.content.parts or []:
            if part.text:
                text_parts.append(part.text)
            if part.function_call is not None:
                function_call = part.function_call
                arguments = function_call.args or {}
                if not isinstance(arguments, Mapping):
                    raise LLMResponseError(
                        f"Gemini arguments for tool {function_call.name} must be an object"
                    )
                tool_calls.append(
                    LLMToolCall(
                        name=function_call.name,
                        arguments=dict(arguments),
                    )
                )

        provider_usage = response.usage_metadata
        usage = (
            LLMUsage(
                prompt_tokens=provider_usage.prompt_token_count,
                completion_tokens=provider_usage.candidates_token_count,
            )
            if provider_usage is not None
            else None
        )
        normalized = LLMResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            usage=usage,
        )
        logger.info(
            "Received LLM completion",
            extra={
                "provider": "gemini",
                "model": self._model,
                "tool_call_count": len(tool_calls),
                "prompt_tokens": usage.prompt_tokens if usage else None,
                "completion_tokens": usage.completion_tokens if usage else None,
            },
        )
        return normalized


def create_llm_client() -> LLMClient:
    """Load dotenv configuration and construct the selected provider client."""
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise LLMConfigurationError(
            "python-dotenv is required to load LLM configuration"
        ) from exc
    load_dotenv()

    # ASSUMPTION: OpenAI is used only when LLM_PROVIDER is unset; Gemini is selectable explicitly.
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "")
    if provider == "openai":
        return OpenAIChatClient(api_key=api_key, model=model)
    if provider == "groq":
        return OpenAIChatClient(
            api_key=api_key,
            model=model,
            base_url="https://api.groq.com/openai/v1",
            provider="groq",
        )
    if provider == "gemini":
        return GeminiChatClient(api_key=api_key, model=model)
    raise LLMConfigurationError(
        f"Unsupported LLM_PROVIDER {provider!r}; configured providers: openai, gemini, groq"
    )
