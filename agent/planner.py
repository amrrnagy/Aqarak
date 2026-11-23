"""Use the configured LLM to select and order allow-listed deterministic tools."""

import json
import logging
from pathlib import Path
from typing import Any

from agent.llm import LLMClient, LLMToolCall
from agent.memory import SessionState

logger = logging.getLogger(__name__)
PROMPT_PATH = Path(__file__).parent / "prompts" / "planner.md"

_FILTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "budget_min": {"type": "number"},
        "budget_max": {"type": "number"},
        "areas": {"type": "array", "items": {"type": "string"}},
        "bedrooms": {"type": "integer"},
        "delivery_by": {"type": "string", "format": "date"},
    },
    "additionalProperties": False,
}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_listings",
            "description": "Search property listings and area/developer reference documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "filters": _FILTER_SCHEMA,
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "installment_calc",
            "description": "Calculate a plan from user-provided price and terms; annual_rate is a decimal fraction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "price": {"type": "number"},
                    "down_payment_pct": {"type": "number"},
                    "years": {"type": "number"},
                    "annual_rate_pct": {
                        "type": "number",
                        "description": "Explicit annual rate in percentage points, e.g. 8 for 8%.",
                    },
                },
                "required": ["price", "down_payment_pct", "years"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "roi_estimator",
            "description": "Estimate gross yield and appreciation from explicitly supplied assumptions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "purchase_price": {"type": "number"},
                    "monthly_rent": {"type": "number"},
                    "annual_appreciation_pct": {"type": "number"},
                    "horizon_years": {"type": "integer"},
                },
                "required": [
                    "purchase_price",
                    "monthly_rent",
                    "annual_appreciation_pct",
                    "horizon_years",
                ],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_plans",
            "description": "Compare plans for existing listings by exact listing IDs; do not invent listing details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "options": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 4,
                        "items": {
                            "type": "object",
                            "properties": {
                                "listing_id": {"type": "string"},
                                "label": {"type": "string"},
                            },
                            "required": ["listing_id"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["options"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_search",
            "description": "Save user-provided listing filters to the current session.",
            "parameters": {
                "type": "object",
                "properties": {"filters": _FILTER_SCHEMA},
                "required": ["filters"],
                "additionalProperties": False,
            },
        },
    },
]


class Planner:
    """Build ordered tool calls from the request and a session snapshot."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client
        self._system_prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def plan(
        self, message: str, language: str, state: SessionState
    ) -> list[LLMToolCall]:
        """Ask the LLM to choose from the fixed set of deterministic tools."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt}
        ]
        for item in state.message_history:
            if item.role == "tool":
                content = f"Verified tool output ({item.tool_name}): {item.content}"
                messages.append({"role": "assistant", "content": content})
            else:
                messages.append({"role": item.role, "content": item.content})
        messages.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "current_request": message,
                        "language": language,
                        "preferences": state.preferences.model_dump(mode="json"),
                        "saved_searches": [
                            search.model_dump(mode="json")
                            for search in state.saved_searches
                        ],
                    },
                    ensure_ascii=False,
                ),
            }
        )
        response = self._llm_client.chat(messages, tools=TOOL_DEFINITIONS)
        logger.info(
            "Planned assistant tools",
            extra={"tool_count": len(response.tool_calls)},
        )
        return response.tool_calls
