"""Streamlit home page for the Aqarak API-backed dashboard."""

import streamlit as st

from ui.api_client import APIClientError, api_request

st.set_page_config(
    page_title="Aqarak",
    layout="wide",
)

st.title("Aqarak")
st.write(
    "Search Egyptian property listings, compare deterministic installment "
    "plans, and review service analytics."
)
st.info(
    "Choose **Chat**, **Compare Plans**, or **Analytics** from the navigation "
    "menu to get started."
)

try:
    health = api_request("GET", "/health")
except APIClientError as exc:
    st.warning(f"API status: unavailable - {exc}")
else:
    st.success(f"API status: {health.get('status', 'unknown')}")
