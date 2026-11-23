"""Provider adapter tests that do not make network requests."""

from types import SimpleNamespace
from typing import Any

from agent.llm import (
    GeminiChatClient,
    LLMResponse,
    LLMProviderError,
    OpenAIChatClient,
    create_llm_client,
)


def test_factory_selects_gemini_from_environment(monkeypatch: Any) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "gemini-test-model")

    client = create_llm_client()

    assert isinstance(client, GeminiChatClient)


def test_factory_selects_groq_openai_compatible_endpoint(monkeypatch: Any) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_API_KEY", "test-groq-key")
    monkeypatch.setenv("LLM_MODEL", "test-groq-model")

    client = create_llm_client()

    assert isinstance(client, OpenAIChatClient)
    assert client._client.base_url == "https://api.groq.com/openai/v1/"
    assert client._model == "test-groq-model"
    assert client._provider == "groq"


def test_gemini_adapter_normalizes_text_and_function_calls() -> None:
    client = GeminiChatClient(api_key="test-key", model="gemini-test-model")
    generated_requests: list[dict[str, Any]] = []
    provider_response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text="planned", function_call=None),
                        SimpleNamespace(
                            text=None,
                            function_call=SimpleNamespace(
                                name="search_listings",
                                args={"query": "New Cairo"},
                            ),
                        ),
                    ]
                )
            )
        ],
        usage_metadata=SimpleNamespace(
            prompt_token_count=12,
            candidates_token_count=4,
        ),
    )

    def generate_content(**kwargs: Any) -> Any:
        generated_requests.append(kwargs)
        return provider_response

    client._client = SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)
    )

    response = client.chat(
        [{"role": "system", "content": "system"}, {"role": "user", "content": "search"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "search_listings",
                    "description": "Find listings",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }
        ],
    )

    assert isinstance(response, LLMResponse)
    assert response.content == "planned"
    assert response.tool_calls[0].name == "search_listings"
    assert response.tool_calls[0].arguments == {"query": "New Cairo"}
    assert response.usage.prompt_tokens == 12
    config = generated_requests[0]["config"]
    assert config.automatic_function_calling.disable is True
    assert config.tools[0].function_declarations[0].name == "search_listings"


def test_gemini_provider_failures_are_normalized() -> None:
    class ProviderUnavailable(Exception):
        code = 503

    client = GeminiChatClient(api_key="test-key", model="gemini-test-model")
    client._api_error = ProviderUnavailable

    def generate_content(**_: Any) -> Any:
        raise ProviderUnavailable("temporary outage")

    client._client = SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)
    )

    try:
        client.chat([{"role": "user", "content": "hello"}])
    except LLMProviderError as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError("Expected a normalized provider error")
