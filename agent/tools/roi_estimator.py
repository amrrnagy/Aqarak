"""Deterministic rental yield and property appreciation estimates."""

import logging
import math

from data.schemas import ROIResult

logger = logging.getLogger(__name__)


class ROIEstimationError(ValueError):
    """Raised when return-estimation inputs are invalid."""


def roi_estimator(
    purchase_price: float,
    monthly_rent: float,
    annual_appreciation_pct: float,
    horizon_years: int,
) -> ROIResult:
    """Estimate gross yield and appreciation from explicit user-supplied inputs.

    Current monthly rent is annualized to calculate gross yield. Property value
    compounds annually at the supplied appreciation rate. The estimate excludes
    vacancy, costs, taxes, and financing.
    """
    values = {
        "purchase_price": purchase_price,
        "monthly_rent": monthly_rent,
        "annual_appreciation_pct": annual_appreciation_pct,
    }
    for name, value in values.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ROIEstimationError(f"{name} must be a finite number")

    if purchase_price <= 0:
        raise ROIEstimationError("purchase_price must be greater than zero")
    if monthly_rent < 0:
        raise ROIEstimationError("monthly_rent cannot be negative")
    if annual_appreciation_pct <= -100:
        raise ROIEstimationError("annual_appreciation_pct must be greater than -100")
    if isinstance(horizon_years, bool) or not isinstance(horizon_years, int):
        raise ROIEstimationError("horizon_years must be a whole number")
    if horizon_years <= 0:
        raise ROIEstimationError("horizon_years must be greater than zero")

    annual_rent = monthly_rent * 12
    try:
        projected_value = purchase_price * (
            1 + annual_appreciation_pct / 100
        ) ** horizon_years
    except OverflowError as exc:
        raise ROIEstimationError(
            "assumptions produce a projected value outside the supported numeric range"
        ) from exc
    if not math.isfinite(annual_rent) or not math.isfinite(projected_value):
        raise ROIEstimationError(
            "assumptions produce a result outside the supported numeric range"
        )
    gross_yield_pct = annual_rent / purchase_price * 100
    appreciation_pct = (projected_value / purchase_price - 1) * 100
    if not math.isfinite(gross_yield_pct) or not math.isfinite(appreciation_pct):
        raise ROIEstimationError(
            "assumptions produce a percentage outside the supported numeric range"
        )
    result = ROIResult(
        purchase_price=round(purchase_price, 2),
        estimated_annual_rent=round(annual_rent, 2),
        gross_yield_pct=round(gross_yield_pct, 4),
        projected_value=round(projected_value, 2),
        appreciation_pct=round(appreciation_pct, 4),
        horizon_years=horizon_years,
        assumptions={
            "monthly_rent_egp": monthly_rent,
            "annual_appreciation_pct": annual_appreciation_pct,
            "horizon_years": horizon_years,
            "annual_rent_calculated_as_monthly_rent_times_12": True,
            "appreciation_compounded_annually": True,
            "excludes_vacancy_costs_taxes_and_financing": True,
        },
    )
    logger.info(
        "Estimated property return",
        extra={
            "purchase_price": result.purchase_price,
            "gross_yield_pct": result.gross_yield_pct,
            "horizon_years": result.horizon_years,
        },
    )
    return result
