"""Tests for side-by-side deterministic plan comparison."""

import pytest

from agent.tools.compare_plans import PlanComparisonError, compare_plans
from agent.tools.installment_calc import installment_calc


def test_comparison_identifies_lowest_total_and_monthly_options() -> None:
    first = installment_calc(3_000_000, 10, 8)
    second = installment_calc(2_800_000, 10, 9)

    result = compare_plans([first, second])

    assert len(result.side_by_side) == 2
    assert result.lowest_total_cost == "option_2"
    assert result.lowest_monthly_payment == "option_2"


@pytest.mark.parametrize("count", [0, 1, 5])
def test_comparison_requires_two_to_four_options(count: int) -> None:
    plans = [installment_calc(100_000, 10, 1)] * count
    with pytest.raises(PlanComparisonError, match="between 2 and 4"):
        compare_plans(plans)
