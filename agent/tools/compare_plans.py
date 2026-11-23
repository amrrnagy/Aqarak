"""Deterministic side-by-side comparison of calculated purchase plans."""

import logging
from typing import Sequence

from data.schemas import (
    PlanComparison,
    PlanComparisonInput,
    PlanComparisonOption,
    PlanResult,
)

logger = logging.getLogger(__name__)


class PlanComparisonError(ValueError):
    """Raised when plan comparison inputs are invalid."""


def compare_plans(
    plans: Sequence[PlanResult | PlanComparisonInput],
) -> PlanComparison:
    """Compare two to four calculated plans, optionally linked to listings.

    Raw listings are not enough to compare payments: each option must include a
    deterministic PlanResult rather than silently assuming financing terms.
    """
    if not 2 <= len(plans) <= 4:
        raise PlanComparisonError("plans must contain between 2 and 4 options")

    options: list[PlanComparisonOption] = []
    for index, value in enumerate(plans, start=1):
        if isinstance(value, PlanResult):
            comparison_input = PlanComparisonInput(plan=value)
        elif isinstance(value, PlanComparisonInput):
            comparison_input = value
        else:
            raise PlanComparisonError(
                f"option {index} must be a PlanResult or PlanComparisonInput"
            )
        options.append(
            PlanComparisonOption(
                option_id=f"option_{index}",
                label=comparison_input.label or f"Option {index}",
                listing=comparison_input.listing,
                plan=comparison_input.plan,
            )
        )

    lowest_total = min(options, key=lambda option: option.plan.total_paid)
    lowest_monthly = min(options, key=lambda option: option.plan.monthly_payment)
    result = PlanComparison(
        side_by_side=options,
        lowest_total_cost=lowest_total.option_id,
        lowest_monthly_payment=lowest_monthly.option_id,
    )
    logger.info(
        "Compared installment plans",
        extra={
            "option_count": len(options),
            "lowest_total_cost": result.lowest_total_cost,
            "lowest_monthly_payment": result.lowest_monthly_payment,
        },
    )
    return result
