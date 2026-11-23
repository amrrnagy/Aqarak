"""Tests for deterministic return estimation."""

import pytest

from agent.tools.roi_estimator import ROIEstimationError, roi_estimator


def test_yield_and_compounded_appreciation_use_explicit_assumptions() -> None:
    # EGP 30,000 monthly rent is EGP 360,000 annually (12% gross yield);
    # EGP 3,000,000 appreciating 5% for 2 years becomes EGP 3,307,500.
    result = roi_estimator(
        purchase_price=3_000_000,
        monthly_rent=30_000,
        annual_appreciation_pct=5,
        horizon_years=2,
    )

    assert result.estimated_annual_rent == 360_000
    assert result.gross_yield_pct == 12
    assert result.projected_value == 3_307_500
    assert result.appreciation_pct == 10.25
    assert result.assumptions["monthly_rent_egp"] == 30_000
    assert result.assumptions["annual_appreciation_pct"] == 5


@pytest.mark.parametrize(
    ("purchase_price", "monthly_rent", "appreciation", "horizon", "message"),
    [
        (0, 1, 5, 1, "purchase_price"),
        (-1, 1, 5, 1, "purchase_price"),
        (100, -1, 5, 1, "monthly_rent"),
        (100, 1, -100, 1, "annual_appreciation_pct"),
        (100, 1, 5, 0, "horizon_years"),
        (100, 1, 5, 1.5, "whole number"),
    ],
)
def test_invalid_assumptions_raise_clear_errors(
    purchase_price: float,
    monthly_rent: float,
    appreciation: float,
    horizon: int,
    message: str,
) -> None:
    with pytest.raises(ROIEstimationError, match=message):
        roi_estimator(purchase_price, monthly_rent, appreciation, horizon)
