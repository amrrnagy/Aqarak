"""Assistant loop for tool planning, deterministic execution, and guarded replies."""

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent.guardrails import NumericGuardrailError, verify_numeric_claims
from agent.llm import LLMClient, LLMToolCall, create_llm_client
from agent.memory import MemoryStore, SessionMemory, SessionState
from agent.planner import Planner
from agent.tools.compare_plans import compare_plans
from agent.tools.installment_calc import installment_calc
from agent.tools.roi_estimator import roi_estimator
from agent.tools.save_search import save_search
from agent.tools.search_listings import search_listings
from data.schemas import (
    ChatRequest,
    ChatResponse,
    Listing,
    PlanComparison,
    PlanComparisonInput,
    PlanComparisonOption,
    PlanResult,
    RetrievedItem,
    SavedSearch,
)
from rag.retriever import HybridRetriever

logger = logging.getLogger(__name__)
SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"


class _ToolArguments(BaseModel):
    """Base class that rejects unexpected model-generated tool parameters."""

    model_config = ConfigDict(extra="forbid")


class _SearchArguments(_ToolArguments):
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)


class _InstallmentArguments(_ToolArguments):
    price: float
    down_payment_pct: float
    years: float
    annual_rate_pct: Optional[float] = None


class _ROIArguments(_ToolArguments):
    purchase_price: float
    monthly_rent: float
    annual_appreciation_pct: float
    horizon_years: int


class _CompareOptionArguments(_ToolArguments):
    listing_id: str
    label: Optional[str] = None


class _CompareArguments(_ToolArguments):
    options: list[_CompareOptionArguments] = Field(min_length=2, max_length=4)


class _SaveSearchArguments(_ToolArguments):
    filters: dict[str, Any]


_ArgumentsT = TypeVar("_ArgumentsT", bound=_ToolArguments)


class ToolExecutionError(ValueError):
    """Raised when a planned tool call is invalid or cannot be fulfilled."""


class AgentExecutionError(RuntimeError):
    """Raised when the model or agent cannot safely complete a turn."""


class Agent:
    """Run one user turn against the configured LLM and deterministic tools."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        memory: Optional[MemoryStore] = None,
        retriever: Optional[HybridRetriever] = None,
    ) -> None:
        self._llm_client = llm_client if llm_client is not None else create_llm_client()
        self._memory = memory if memory is not None else SessionMemory()
        self._retriever = retriever if retriever is not None else HybridRetriever()
        self._planner = Planner(self._llm_client)
        self._system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Plan and execute tools, synthesize only from outputs, then verify."""
        if not request.message.strip():
            raise ValueError("message must not be empty")
        started = time.perf_counter()
        state = self._memory.get_state(request.session_id)
        calls = self._planner.plan(request.message, request.language, state)
        self._memory.add_message(request.session_id, "user", request.message)

        tool_outputs: list[Any] = []
        for call in calls:
            output = self._execute(call, request, state)
            tool_outputs.append(output)
            serialized = self._json_value(output)
            self._memory.add_message(
                request.session_id,
                "tool",
                json.dumps(serialized, ensure_ascii=False, sort_keys=True),
                tool_name=call.name,
            )

        previous_outputs = self._previous_tool_outputs(state)
        verified_outputs = previous_outputs + tool_outputs
        reply = self._synthesize(request, verified_outputs)
        verification = verify_numeric_claims(reply, verified_outputs)
        if not verification.verified:
            logger.warning(
                "Regenerating reply with unsupported numeric claims",
                extra={"unsupported_count": len(verification.unsupported_numbers)},
            )
            reply = self._regenerate(
                request, verified_outputs, reply, verification.unsupported_numbers
            )
            verification = verify_numeric_claims(reply, verified_outputs)
        if not verification.verified:
            raise NumericGuardrailError(verification.unsupported_numbers)

        self._memory.add_message(request.session_id, "assistant", reply)
        listings, plans, sources = self._collect_results(tool_outputs)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "Completed assistant turn",
            extra={
                "session_id": request.session_id,
                "tool_call_count": len(calls),
                "listing_count": len(listings),
                "latency_ms": latency_ms,
            },
        )
        return ChatResponse(
            reply=reply,
            tool_calls_used=[call.name for call in calls],
            sources=sources,
            listings=listings,
            plans=plans,
            cached=False,
            latency_ms=latency_ms,
        )

    def _execute(
        self, call: LLMToolCall, request: ChatRequest, state: SessionState
    ) -> Any:
        """Validate and dispatch one allow-listed tool call."""
        if call.name == "search_listings":
            arguments = self._parse_arguments(_SearchArguments, call)
            self._verify_numeric_inputs(
                call,
                {"filters": arguments.filters},
                request,
                state,
            )
            return search_listings(
                arguments.query, arguments.filters, self._retriever
            )
        if call.name == "installment_calc":
            arguments = self._parse_arguments(_InstallmentArguments, call)
            self._verify_numeric_inputs(call, call.arguments, request, state)
            # ASSUMPTION: planner rates are percentage points; installment_calc uses decimal fractions.
            annual_rate = (
                arguments.annual_rate_pct / 100
                if arguments.annual_rate_pct is not None
                else 0.0
            )
            return installment_calc(
                arguments.price,
                arguments.down_payment_pct,
                arguments.years,
                annual_rate=annual_rate,
            )
        if call.name == "roi_estimator":
            arguments = self._parse_arguments(_ROIArguments, call)
            self._verify_numeric_inputs(call, call.arguments, request, state)
            return roi_estimator(
                purchase_price=arguments.purchase_price,
                monthly_rent=arguments.monthly_rent,
                annual_appreciation_pct=arguments.annual_appreciation_pct,
                horizon_years=arguments.horizon_years,
            )
        if call.name == "compare_plans":
            arguments = self._parse_arguments(_CompareArguments, call)
            available: list[PlanComparisonInput] = []
            unavailable: list[dict[str, Any]] = []
            for option in arguments.options:
                listing = self._retriever.get_listing(option.listing_id)
                if listing is None:
                    unavailable.append(
                        {"listing_id": option.listing_id, "reason": "not found"}
                    )
                    continue
                if (
                    listing.price is None
                    or listing.down_payment_pct is None
                    or listing.installment_years is None
                ):
                    missing = [
                        field
                        for field in (
                            "price",
                            "down_payment_pct",
                            "installment_years",
                        )
                        if getattr(listing, field) is None
                    ]
                    unavailable.append(
                        {
                            "listing_id": option.listing_id,
                            "listing": listing,
                            "missing_fields": missing,
                        }
                    )
                    continue
                # ASSUMPTION: sample developer installment plans use the documented 0% default.
                plan = installment_calc(
                    price=listing.price,
                    down_payment_pct=listing.down_payment_pct,
                    years=listing.installment_years,
                )
                available.append(
                    PlanComparisonInput(
                        label=option.label,
                        listing=listing,
                        plan=plan,
                    )
                )
            comparison: Optional[PlanComparison] = (
                compare_plans(available) if len(available) >= 2 else None
            )
            return {
                "comparison": comparison,
                "available_options": available if comparison is None else [],
                "unavailable_options": unavailable,
            }
        if call.name == "save_search":
            arguments = self._parse_arguments(_SaveSearchArguments, call)
            self._verify_numeric_inputs(
                call,
                {"filters": arguments.filters},
                request,
                state,
            )
            return save_search(
                request.session_id, arguments.filters, self._memory
            )
        raise ToolExecutionError(f"Unsupported tool requested by planner: {call.name}")

    @staticmethod
    def _parse_arguments(
        model: type[_ArgumentsT], call: LLMToolCall
    ) -> _ArgumentsT:
        try:
            return model.model_validate(call.arguments)
        except ValidationError as exc:
            raise ToolExecutionError(
                f"Invalid arguments for tool {call.name}: {exc}"
            ) from exc

    @staticmethod
    def _verify_numeric_inputs(
        call: LLMToolCall,
        arguments: dict[str, Any],
        request: ChatRequest,
        state: SessionState,
    ) -> None:
        """Reject calculated or invented numeric tool inputs before execution."""
        sources: list[Any] = [
            request.message,
            state.preferences,
            state.saved_searches,
        ]
        sources.extend(
            item.content
            for item in state.message_history
            if item.role in ("user", "tool")
        )
        verification = verify_numeric_claims(
            json.dumps(arguments, ensure_ascii=False), sources
        )
        if not verification.verified:
            raise ToolExecutionError(
                f"Tool {call.name} included unsupported numeric inputs: "
                + ", ".join(verification.unsupported_numbers)
            )

    def _synthesize(
        self, request: ChatRequest, tool_outputs: list[Any]
    ) -> str:
        """Generate a reply from the request and verified current/prior tool data."""
        messages = self._synthesis_messages(request, tool_outputs)
        response = self._llm_client.chat(messages)
        if response.tool_calls:
            raise AgentExecutionError("Synthesis response unexpectedly requested tools")
        return response.content.strip()

    def _regenerate(
        self,
        request: ChatRequest,
        tool_outputs: list[Any],
        rejected_reply: str,
        unsupported_numbers: list[str],
    ) -> str:
        """Retry synthesis once with explicit guardrail feedback."""
        messages = self._synthesis_messages(request, tool_outputs)
        messages.extend(
            [
                {"role": "assistant", "content": rejected_reply},
                {
                    "role": "user",
                    "content": (
                        "Rewrite the reply using only supported facts and numbers. "
                        "Remove unsupported numeric claims and do not replace them "
                        f"with guesses. Unsupported claims: {unsupported_numbers}"
                    ),
                },
            ]
        )
        response = self._llm_client.chat(messages)
        if response.tool_calls:
            raise AgentExecutionError("Regenerated response unexpectedly requested tools")
        return response.content.strip()

    def _synthesis_messages(
        self, request: ChatRequest, tool_outputs: list[Any]
    ) -> list[dict[str, str]]:
        context = {
            "language": request.language,
            "user_request": request.message,
            "verified_tool_outputs": [
                self._json_value(output)
                for output in tool_outputs
            ],
        }
        return [
            {"role": "system", "content": self._system_prompt},
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, sort_keys=True),
            },
        ]

    @staticmethod
    def _previous_tool_outputs(state: SessionState) -> list[Any]:
        """Load only serialized prior tool results, never prior assistant claims."""
        return [
            json.loads(item.content)
            for item in state.message_history
            if item.role == "tool"
        ]

    @classmethod
    def _json_value(cls, value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return {key: cls._json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_value(item) for item in value]
        return value

    @staticmethod
    def _collect_results(
        outputs: list[Any],
    ) -> tuple[list[Listing], list[PlanResult], list[str]]:
        listings: dict[str, Listing] = {}
        plans: list[PlanResult] = []
        sources: list[str] = []

        def visit(value: Any) -> None:
            if isinstance(value, RetrievedItem):
                if value.source not in sources:
                    sources.append(value.source)
                if value.listing is not None:
                    listings[value.listing.id] = value.listing
                return
            if isinstance(value, Listing):
                listings[value.id] = value
                source = f"data/raw/listings.csv#{value.id}"
                if source not in sources:
                    sources.append(source)
                return
            if isinstance(value, PlanResult):
                plans.append(value)
                return
            if isinstance(value, PlanComparisonOption):
                if value.listing is not None:
                    visit(value.listing)
                visit(value.plan)
                return
            if isinstance(value, PlanComparison):
                for option in value.side_by_side:
                    visit(option)
                return
            if isinstance(value, PlanComparisonInput):
                if value.listing is not None:
                    visit(value.listing)
                visit(value.plan)
                return
            if isinstance(value, SavedSearch):
                return
            if isinstance(value, dict):
                for item in value.values():
                    visit(item)
                return
            if isinstance(value, (list, tuple)):
                for item in value:
                    visit(item)

        for output in outputs:
            visit(output)
        return list(listings.values()), plans, sources
