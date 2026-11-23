"""Ten mocked assistant conversations covering tools, memory, and guardrails."""

from typing import Any, Mapping, Optional, Sequence

import pytest

from agent.agent import Agent, ToolExecutionError
from agent.guardrails import verify_numeric_claims
from agent.llm import LLMClient, LLMResponse, LLMToolCall
from agent.memory import SessionMemory
from data.schemas import ChatRequest, Listing, RetrievedItem


class MockLLM(LLMClient):
    """Return scripted planner and synthesis responses without network access."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[list[Mapping[str, Any]], Sequence[Mapping[str, Any]]]] = []

    def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] = (),
    ) -> LLMResponse:
        self.calls.append((list(messages), tools))
        if not self.responses:
            raise AssertionError("MockLLM received an unexpected call")
        return self.responses.pop(0)


class MockRetriever:
    """Return supplied listing fixtures and support exact-ID lookup."""

    def __init__(self, listings: list[Listing]) -> None:
        self.listings = {listing.id: listing for listing in listings}

    def retrieve(
        self,
        query: str,
        filters: Optional[Mapping[str, Any]] = None,
    ) -> list[RetrievedItem]:
        matches = list(self.listings.values())
        if filters and filters.get("areas"):
            matches = [
                listing
                for listing in matches
                if listing.area in filters["areas"]
            ]
        query_tokens = set(query.lower().split())
        ranked = []
        for listing in matches:
            content = listing.description or listing.title
            content_tokens = set(content.lower().split())
            score = len(query_tokens & content_tokens) / max(len(query_tokens), 1)
            ranked.append(
                RetrievedItem(
                    id=f"listing:{listing.id}",
                    content=content,
                    source=f"data/raw/listings.csv#{listing.id}",
                    kind="listing",
                    score=score,
                    listing=listing,
                )
            )
        return sorted(
            ranked,
            key=lambda item: item.score if item.score is not None else -1,
            reverse=True,
        )

    def get_listing(self, listing_id: str) -> Optional[Listing]:
        return self.listings.get(listing_id)


def _listing(
    listing_id: str = "NC-001",
    *,
    price: Optional[float] = 3_000_000,
    delivery_date: Optional[str] = "2028-06-30",
    area: str = "New Cairo",
) -> Listing:
    return Listing(
        id=listing_id,
        title="Sample family apartment",
        area=area,
        city=area,
        developer="Fictional Homes",
        price=price,
        area_sqm=140,
        bedrooms=2,
        bathrooms=2,
        delivery_date=delivery_date,
        down_payment_pct=10,
        installment_years=8,
        description="SAMPLE listing near parks and retail.",
        property_type="Apartment",
    )


def _tool(name: str, **arguments: Any) -> LLMToolCall:
    return LLMToolCall(name=name, arguments=arguments)


def _scenario_data() -> list[
    tuple[str, str, list[LLMToolCall], list[Listing], list[str], str, bool]
]:
    listing = _listing()
    arabic_listing = _listing("NC-AR")
    compound_listing = _listing("NAC-001", area="New Administrative Capital")
    comparison_listings = [
        _listing("NAC-001", price=3_000_000, area="New Administrative Capital"),
        _listing("NC-001", price=2_800_000),
    ]
    missing_price = _listing("MISSING-PRICE", price=None)
    missing_delivery = _listing("MISSING-DATE", delivery_date=None)
    cases = [
        (
            "Find apartments in New Cairo.",
            "en",
            [_tool("search_listings", query="apartments in New Cairo")],
            [listing],
            ["search_listings"],
            "A sample apartment is listed for EGP 3,000,000.",
            False,
        ),
        (
            "ابحث عن شقة في القاهرة الجديدة",
            "ar",
            [_tool("search_listings", query="شقة في القاهرة الجديدة")],
            [arabic_listing],
            ["search_listings"],
            "السعر في العينة هو ٣٬٠٠٠٬٠٠٠ جنيه.",
            False,
        ),
        (
            "Find an apartment and calculate payments for EGP 3,000,000, 10% down, over 8 years.",
            "en",
            [
                _tool("search_listings", query="apartment"),
                _tool(
                    "installment_calc",
                    price=3_000_000,
                    down_payment_pct=10,
                    years=8,
                ),
            ],
            [compound_listing],
            ["search_listings", "installment_calc"],
            "The calculated monthly installment is EGP 28,125.",
            False,
        ),
        (
            "Calculate a mortgage on EGP 100,000, 10% down, for 1 year at 12%.",
            "en",
            [
                _tool(
                    "installment_calc",
                    price=100_000,
                    down_payment_pct=10,
                    years=1,
                    annual_rate_pct=12,
                )
            ],
            [],
            ["installment_calc"],
            "The monthly mortgage payment is EGP 7,996.39.",
            False,
        ),
        (
            "Compare listings NAC-001 and NC-001.",
            "en",
            [
                _tool(
                    "compare_plans",
                    options=[
                        {"listing_id": "NAC-001", "label": "Capital"},
                        {"listing_id": "NC-001", "label": "New Cairo"},
                    ],
                )
            ],
            comparison_listings,
            ["compare_plans"],
            "Both plans were compared using the stored listing terms.",
            False,
        ),
        (
            "Estimate ROI for EGP 3,000,000 purchase price, EGP 30,000 monthly rent, 5% appreciation, over 2 years.",
            "en",
            [
                _tool(
                    "roi_estimator",
                    purchase_price=3_000_000,
                    monthly_rent=30_000,
                    annual_appreciation_pct=5,
                    horizon_years=2,
                )
            ],
            [],
            ["roi_estimator"],
            "The gross yield is 12%, and the projected value is EGP 3,307,500.",
            False,
        ),
        (
            "Find listing MISSING-PRICE.",
            "en",
            [_tool("search_listings", query="MISSING-PRICE")],
            [missing_price],
            ["search_listings"],
            "The listing does not provide a price.",
            False,
        ),
        (
            "Find listing MISSING-DATE and tell me when it is delivered.",
            "en",
            [_tool("search_listings", query="MISSING-DATE delivery date")],
            [missing_delivery],
            ["search_listings"],
            "The delivery date is unavailable in the sample listing.",
            False,
        ),
        (
            "Save my New Cairo search under 5,000,000 EGP.",
            "en",
            [
                _tool(
                    "save_search",
                    filters={"areas": ["New Cairo"], "budget_max": 5_000_000},
                )
            ],
            [],
            ["save_search"],
            "Saved to this session.",
            False,
        ),
        (
            "Find apartments in New Cairo.",
            "en",
            [_tool("search_listings", query="apartments in New Cairo")],
            [listing],
            ["search_listings"],
            "The sample listing price is EGP 3M.",
            True,
        ),
    ]
    return cases


@pytest.mark.parametrize(
    (
        "message",
        "language",
        "calls",
        "listings",
        "expected_tools",
        "expected_reply",
        "needs_regeneration",
    ),
    _scenario_data(),
    ids=[
        "simple-search",
        "arabic-search",
        "compound-search-and-plan",
        "mortgage",
        "plan-comparison",
        "roi",
        "missing-price",
        "missing-delivery-date",
        "save-search",
        "guardrail-regeneration",
    ],
)
def test_ten_scripted_agent_conversations(
    message: str,
    language: str,
    calls: list[LLMToolCall],
    listings: list[Listing],
    expected_tools: list[str],
    expected_reply: str,
    needs_regeneration: bool,
) -> None:
    replies = [LLMResponse(tool_calls=calls)]
    if needs_regeneration:
        replies.append(LLMResponse(content="This listing costs EGP 4,000,000."))
    replies.append(LLMResponse(content=expected_reply))

    llm = MockLLM(replies)
    memory = SessionMemory()
    agent = Agent(
        llm_client=llm,
        memory=memory,
        retriever=MockRetriever(listings),  # type: ignore[arg-type]
    )
    response = agent.chat(
        ChatRequest(session_id="test-session", message=message, language=language)
    )

    assert response.tool_calls_used == expected_tools
    assert response.reply == expected_reply
    assert memory.get_state("test-session").message_history[-1].role == "assistant"
    assert llm.calls[0][1]
    assert llm.calls[-1][1] == ()


def test_calculation_tool_inputs_cannot_be_invented_by_planner() -> None:
    llm = MockLLM(
        [
            LLMResponse(
                tool_calls=[
                    _tool(
                        "installment_calc",
                        price=9_999_999,
                        down_payment_pct=10,
                        years=8,
                    )
                ]
            )
        ]
    )
    agent = Agent(
        llm_client=llm,
        memory=SessionMemory(),
        retriever=MockRetriever([]),  # type: ignore[arg-type]
    )

    with pytest.raises(ToolExecutionError, match="unsupported numeric inputs"):
        agent.chat(
            ChatRequest(
                session_id="untrusted-plan",
                message="Calculate the installment plan for a property.",
                language="en",
            )
        )


def test_numeric_guardrail_allows_equivalent_formats_and_rejects_new_values() -> None:
    assert verify_numeric_claims(
        "The price is 3.25M EGP (٣٬٢٥٠٬٠٠٠).", [3_250_000]
    ).verified
    assert verify_numeric_claims("five million EGP", [5_000_000]).verified
    assert verify_numeric_claims("خمسة ملايين جنيه", [5_000_000]).verified
    result = verify_numeric_claims("The price is 4,000,000 EGP.", [3_250_000])
    assert not result.verified
    assert result.unsupported_numbers == ["4,000,000"]
