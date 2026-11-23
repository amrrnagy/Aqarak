"""Shared Pydantic contracts for Aqarak data and API payloads."""

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Listing(BaseModel):
    """A property listing, with unavailable source data represented as null."""

    id: str
    title: str
    area: Optional[str] = None
    city: Optional[str] = None
    developer: Optional[str] = None
    price: Optional[float] = None
    area_sqm: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    delivery_date: Optional[date] = None
    down_payment_pct: Optional[float] = None
    installment_years: Optional[float] = None
    description: Optional[str] = None
    property_type: Optional[str] = None


class Developer(BaseModel):
    """A real estate developer and its delivery track record."""

    id: str
    name: str
    track_record_summary: Optional[str] = None
    projects_delivered: Optional[int] = None


class PlanResult(BaseModel):
    """Deterministic installment plan figures for a property's purchase."""

    price: float
    down_payment: float
    financed_amount: float
    monthly_payment: float
    total_paid: float
    total_interest: float
    annual_rate: float
    years: float
    schedule_summary: str


class ROIResult(BaseModel):
    """Estimated return figures and the assumptions used to derive them."""

    purchase_price: float
    estimated_annual_rent: float
    gross_yield_pct: float
    projected_value: float
    appreciation_pct: float
    horizon_years: int
    assumptions: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    """A user's message and language preference for an assistant session."""

    session_id: str
    message: str
    language: Literal["ar", "en"]


class ChatResponse(BaseModel):
    """The assistant reply and supporting structured results."""

    reply: str
    tool_calls_used: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    listings: list[Listing] = Field(default_factory=list)
    plans: list[PlanResult] = Field(default_factory=list)
    cached: bool = False
    latency_ms: float


class UserPreferences(BaseModel):
    """Optional filters and priorities saved for a user's property searches."""

    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    areas: list[str] = Field(default_factory=list)
    bedrooms: Optional[int] = None
    delivery_by: Optional[date] = None
    investment_focus: Optional[str] = None


class PlanComparisonInput(BaseModel):
    """A calculated plan, optionally associated with its source listing."""

    label: Optional[str] = None
    listing: Optional[Listing] = None
    plan: PlanResult


class PlanComparisonOption(BaseModel):
    """One labeled option in a side-by-side plan comparison."""

    option_id: str
    label: str
    listing: Optional[Listing] = None
    plan: PlanResult


class PlanComparison(BaseModel):
    """Comparable plan options and the lowest-cost and lowest-payment IDs."""

    side_by_side: list[PlanComparisonOption]
    lowest_total_cost: str
    lowest_monthly_payment: str


class RetrievedItem(BaseModel):
    """A semantically retrieved listing or knowledge document with attribution."""

    id: str
    content: str
    source: str
    kind: Literal["listing", "area_guide", "developer"]
    score: Optional[float] = None
    listing: Optional[Listing] = None


class SavedSearch(BaseModel):
    """A timestamped set of filters retained in session memory."""

    id: str
    session_id: str
    filters: UserPreferences
    created_at: datetime


class RetrievalEvaluationResult(BaseModel):
    """Hit/miss details for one retrieval evaluation query."""

    query: str
    expected_listing_id: str
    found: bool


class RetrievalEvaluation(BaseModel):
    """Aggregate retrieval hit rate and per-query outcomes."""

    query_count: int
    hit_count: int
    hit_rate: float
    results: list[RetrievalEvaluationResult]


class IngestionSummary(BaseModel):
    """Counts of records accepted and indexed by one ingestion run."""

    valid_listings: int
    invalid_listings: int
    knowledge_chunks: int
