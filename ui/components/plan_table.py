"""Reusable side-by-side installment plan comparison component."""

from typing import Any, Mapping

import streamlit as st


_LABELS = {
    "en": {
        "down_payment": "Down payment",
        "financed": "Financed",
        "monthly": "Monthly payment",
        "total_paid": "Total paid",
        "interest": "Total interest",
        "lowest_cost": "Lowest total cost",
        "lowest_monthly": "Lowest monthly payment",
    },
    "ar": {
        "down_payment": "المقدم",
        "financed": "المبلغ الممول",
        "monthly": "القسط الشهري",
        "total_paid": "إجمالي المدفوع",
        "interest": "إجمالي الفائدة",
        "lowest_cost": "أقل تكلفة إجمالية",
        "lowest_monthly": "أقل قسط شهري",
    },
}


def render_plan_comparison(
    comparison: Mapping[str, Any],
    language: str = "en",
) -> None:
    """Render calculation results and lowest-cost indicators from the API."""
    labels = _LABELS.get(language, _LABELS["en"])
    options = comparison.get("side_by_side", [])
    columns = st.columns(len(options))
    for column, option in zip(columns, options):
        plan = option["plan"]
        listing = option.get("listing") or {}
        with column:
            st.subheader(option.get("label") or listing.get("title") or "Plan")
            if listing.get("id"):
                st.caption(str(listing["id"]))
            if listing.get("price") is None:
                st.caption("Price unavailable")
            else:
                st.metric("Price", f"EGP {listing['price']:,.0f}")
            st.metric(labels["down_payment"], f"EGP {plan['down_payment']:,.0f}")
            st.metric(labels["financed"], f"EGP {plan['financed_amount']:,.0f}")
            st.metric(labels["monthly"], f"EGP {plan['monthly_payment']:,.2f}")
            st.metric(labels["total_paid"], f"EGP {plan['total_paid']:,.0f}")
            st.caption(
                f'{labels["interest"]}: EGP {plan["total_interest"]:,.0f} | '
                f'{plan["years"]:g} years'
            )
            if option["option_id"] == comparison.get("lowest_total_cost"):
                st.success(labels["lowest_cost"])
            if option["option_id"] == comparison.get("lowest_monthly_payment"):
                st.info(labels["lowest_monthly"])
