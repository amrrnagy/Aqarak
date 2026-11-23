"""Versioned deterministic plan comparison API route."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.tools.compare_plans import compare_plans
from agent.tools.installment_calc import (
    InstallmentCalculationError,
    installment_calc,
)
from api.auth import enforce_rate_limit
from api.dependencies import get_retriever
from api.errors import APIError
from data.schemas import PlanComparison, PlanComparisonInput
from rag.retriever import HybridRetriever

router = APIRouter(prefix="/v1", tags=["plans"])


class PlanComparisonRequest(BaseModel):
    """Listing identifiers to compare using their stored installment terms."""

    model_config = ConfigDict(extra="forbid")

    listing_ids: list[str] = Field(min_length=2, max_length=4)

    @field_validator("listing_ids")
    @classmethod
    def validate_listing_ids(cls, values: list[str]) -> list[str]:
        if any(not listing_id.strip() for listing_id in values):
            raise ValueError("listing IDs must not be empty")
        if len(set(values)) != len(values):
            raise ValueError("listing IDs must be unique")
        return values


@router.post("/compare-plans", response_model=PlanComparison)
def compare_listing_plans(
    payload: PlanComparisonRequest,
    request: Request,
    _: str = Depends(enforce_rate_limit),
    retriever: HybridRetriever = Depends(get_retriever),
) -> PlanComparison:
    """Calculate and compare plans only when listing terms are available."""
    inputs: list[PlanComparisonInput] = []
    missing: list[dict[str, object]] = []

    for listing_id in payload.listing_ids:
        try:
            listing = retriever.get_listing(listing_id)
        except FileNotFoundError as exc:
            raise APIError(
                status_code=503,
                code="LISTINGS_NOT_INGESTED",
                message="The sample listing data is not available. Run data ingestion first.",
            ) from exc
        if listing is None:
            missing.append({"listing_id": listing_id, "reason": "not found"})
            continue
        if (
            listing.price is None
            or listing.down_payment_pct is None
            or listing.installment_years is None
        ):
            missing_fields = [
                field
                for field in ("price", "down_payment_pct", "installment_years")
                if getattr(listing, field) is None
            ]
            missing.append(
                {
                    "listing_id": listing_id,
                    "reason": "required plan data is missing",
                    "missing_fields": missing_fields,
                }
            )
            continue
        # ASSUMPTION: The sample listing schema has no developer rate; use the 0% default.
        try:
            plan = installment_calc(
                price=listing.price,
                down_payment_pct=listing.down_payment_pct,
                years=listing.installment_years,
            )
        except InstallmentCalculationError as exc:
            raise APIError(
                status_code=422,
                code="INVALID_PLAN_DATA",
                message=f"Listing {listing_id} has invalid installment data.",
            ) from exc
        inputs.append(
            PlanComparisonInput(
                label=listing.title,
                listing=listing,
                plan=plan,
            )
        )

    if missing:
        raise APIError(
            status_code=422,
            code="PLAN_DATA_UNAVAILABLE",
            message="Some selected listings cannot be compared because required data is unavailable.",
            details=missing,
        )

    comparison = compare_plans(inputs)
    request.state.areas = [
        option.listing.area
        for option in comparison.side_by_side
        if option.listing is not None and option.listing.area
    ]
    request.state.listing_ids = payload.listing_ids
    return comparison
