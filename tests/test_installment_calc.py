"""Tests for deterministic installment calculations."""

import pytest

from agent.tools.installment_calc import (
    InstallmentCalculationError,
    installment_calc,
)


def test_zero_rate_splits_financed_amount_into_equal_months() -> None:
    # EGP 3,000,000 at 10% down leaves EGP 2,700,000 / 96 = EGP 28,125.
    result = installment_calc(3_000_000, 10, 8)

    assert result.down_payment == 300_000
    assert result.financed_amount == 2_700_000
    assert result.monthly_payment == 28_125
    assert result.total_paid == 3_000_000
    assert result.total_interest == 0


def test_positive_rate_uses_monthly_amortization() -> None:
    # 90,000 principal, 1% monthly rate, 12 months: payment rounds to 7,996.39.
    result = installment_calc(100_000, 10, 1, annual_rate=0.12)

    assert result.financed_amount == 90_000
    assert result.monthly_payment == 7_996.39
    assert result.total_interest == 5_956.68


@pytest.mark.parametrize(
    ("price", "down_payment_pct", "years", "annual_rate", "message"),
    [
        (0, 10, 1, 0, "price"),
        (-1, 10, 1, 0, "price"),
        (100, 100, 1, 0, "down_payment_pct"),
        (100, -1, 1, 0, "down_payment_pct"),
        (100, 10, 0, 0, "years"),
        (100, 10, -1, 0, "years"),
        (100, 10, 1, -0.01, "annual_rate"),
    ],
)
def test_invalid_inputs_raise_clear_errors(
    price: float,
    down_payment_pct: float,
    years: float,
    annual_rate: float,
    message: str,
) -> None:
    with pytest.raises(InstallmentCalculationError, match=message):
        installment_calc(price, down_payment_pct, years, annual_rate)
