"""Plan search and comparison page backed exclusively by the API."""

import streamlit as st

from ui.api_client import APIClientError, api_request
from ui.components.plan_table import render_plan_comparison

st.set_page_config(page_title="Compare Plans", layout="wide")
st.title("Compare Installment Plans")
st.write(
    "Search the sample inventory, select two to four listings, and compare "
    "plans calculated from their stored terms."
)

with st.form("listing-search"):
    query = st.text_input("Search listings", value="apartments")
    areas = st.multiselect(
        "Areas",
        [
            "New Administrative Capital",
            "New Cairo",
            "6th of October",
            "Sheikh Zayed",
            "North Coast",
            "Ain Sokhna",
        ],
    )
    search_submitted = st.form_submit_button("Search")

if search_submitted:
    params = {"query": query, "limit": 10}
    if areas:
        params["areas"] = areas
    try:
        st.session_state.plan_candidates = api_request(
            "GET",
            "/v1/listings",
            params=params,
        )
    except APIClientError as exc:
        st.error(str(exc))
    else:
        st.session_state.plan_comparison = None

candidates = st.session_state.get("plan_candidates", [])
if not candidates:
    st.info("Search to load listings that have plan terms available.")
else:
    labels = {
        listing["id"]: (
            f'{listing["title"]} ({listing["id"]})'
            + (
                f' - EGP {listing["price"]:,.0f}'
                if listing.get("price") is not None
                else " - price unavailable"
            )
        )
        for listing in candidates
    }
    selected_ids = st.multiselect(
        "Choose 2-4 listings",
        options=list(labels),
        format_func=lambda listing_id: labels[listing_id],
        max_selections=4,
        key="selected_plan_ids",
    )
    if st.button("Compare selected plans", type="primary"):
        if len(selected_ids) < 2:
            st.error("Select at least two listings.")
        else:
            try:
                st.session_state.plan_comparison = api_request(
                    "POST",
                    "/v1/compare-plans",
                    json={"listing_ids": selected_ids},
                )
            except APIClientError as exc:
                st.error(str(exc))
                if exc.details:
                    st.json(exc.details)

comparison = st.session_state.get("plan_comparison")
if comparison:
    st.subheader("Comparison")
    render_plan_comparison(comparison)
