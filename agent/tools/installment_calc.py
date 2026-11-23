"""Deterministic developer installment and bank mortgage calculations."""

import logging
import math

from data.schemas import PlanResult

logger = logging.getLogger(__name__)


class InstallmentCalculationError(ValueError):
    """Raised when an installment plan input is invalid."""


def installment_calc(
    price: float,
    down_payment_pct: float,
    years: float,
    annual_rate: float = 0.0,
) -> PlanResult:
    """Calculate a plan; ``annual_rate`` is a decimal fraction (e.g. 0.08).

    A zero rate splits principal into equal monthly installments. Positive rates
    use monthly amortization. Inputs are EGP, percent for down_payment_pct, and
    years for duration.
    """
    values = {
        "price": price,
        "down_payment_pct": down_payment_pct,
        "years": years,
        "annual_rate": annual_rate,
    }
    for name, value in values.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise InstallmentCalculationError(f"{name} must be a finite number")

    if price <= 0:
        raise InstallmentCalculationError("price must be greater than zero")
    if not 0 <= down_payment_pct < 100:
        raise InstallmentCalculationError(
            "down_payment_pct must be at least 0 and less than 100"
        )
    if years <= 0:
        raise InstallmentCalculationError("years must be greater than zero")
    if annual_rate < 0:
        raise InstallmentCalculationError("annual_rate cannot be negative")

    month_count = years * 12
    if not math.isfinite(month_count):
        raise InstallmentCalculationError(
            "years must result in a supported number of monthly installments"
        )
    rounded_months = round(month_count)
    if not math.isclose(month_count, rounded_months, abs_tol=1e-9):
        raise InstallmentCalculationError(
            "years must result in a whole number of monthly installments"
        )
    months = rounded_months

    down_payment = price * down_payment_pct / 100
    financed_amount = price - down_payment
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        monthly_payment = financed_amount / months
    else:
        try:
            factor = (1 + monthly_rate) ** months
            monthly_payment = (
                financed_amount * monthly_rate * factor / (factor - 1)
            )
        except OverflowError as exc:
            raise InstallmentCalculationError(
                "inputs produce an installment outside the supported numeric range"
            ) from exc
    if not math.isfinite(monthly_payment):
        raise InstallmentCalculationError(
            "inputs produce an installment outside the supported numeric range"
        )

    down_payment = round(down_payment, 2)
    financed_amount = round(financed_amount, 2)
    monthly_payment = round(monthly_payment, 2)
    total_paid = round(down_payment + monthly_payment * months, 2)
    total_interest = round(total_paid - price, 2)
    if not math.isfinite(total_paid) or not math.isfinite(total_interest):
        raise InstallmentCalculationError(
            "inputs produce totals outside the supported numeric range"
        )
    schedule_summary = (
        f"{months} monthly installments of EGP {monthly_payment:,.2f}; "
        f"down payment EGP {down_payment:,.2f}; annual rate "
        f"{annual_rate * 100:.2f}%."
    )

    result = PlanResult(
        price=round(price, 2),
        down_payment=down_payment,
        financed_amount=financed_amount,
        monthly_payment=monthly_payment,
        total_paid=total_paid,
        total_interest=total_interest,
        annual_rate=annual_rate,
        years=years,
        schedule_summary=schedule_summary,
    )
    logger.info(
        "Calculated installment plan",
        extra={
            "price": result.price,
            "annual_rate": result.annual_rate,
            "years": result.years,
            "monthly_payment": result.monthly_payment,
        },
    )
    return result
