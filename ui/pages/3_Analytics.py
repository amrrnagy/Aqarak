"""Operational analytics page driven by the API metrics endpoint."""

import pandas as pd
import streamlit as st

from ui.api_client import APIClientError, api_request

st.set_page_config(page_title="Aqarak Analytics", layout="wide")
st.title("Analytics")

try:
    metrics = api_request("GET", "/v1/metrics")
except APIClientError as exc:
    st.error(str(exc))
    st.stop()

token_usage = metrics.get("token_usage", {})
first, second, third, fourth = st.columns(4)
first.metric("API requests", metrics.get("request_count", 0))
second.metric("Average latency", f'{metrics.get("average_latency_ms", 0):,.2f} ms')
third.metric("Cache hit rate", f'{metrics.get("cache_hit_rate", 0) * 100:.1f}%')
fourth.metric("LLM tokens", token_usage.get("total_tokens", 0))

latency_series = metrics.get("latency_series", [])
st.subheader("Request latency")
if latency_series:
    latency_frame = pd.DataFrame(latency_series).set_index("timestamp")
    st.line_chart(latency_frame["latency_ms"])
else:
    st.info("Latency data will appear after API requests are made.")

cache_series = metrics.get("cache_series", [])
st.subheader("Listing search cache")
if cache_series:
    cache_frame = pd.DataFrame(
        [
            {
                "timestamp": entry["timestamp"],
                "cache hit (%)": 100 if entry["hit"] else 0,
            }
            for entry in cache_series
        ]
    ).set_index("timestamp")
    st.line_chart(cache_frame)
else:
    st.info("No cacheable listing searches have been recorded yet.")

areas = metrics.get("area_request_counts", [])
listings = metrics.get("most_viewed_listings", [])
area_column, listing_column = st.columns(2)
with area_column:
    st.subheader("Requests by area")
    if areas:
        area_frame = pd.DataFrame(areas).set_index("area")
        st.bar_chart(area_frame["count"])
    else:
        st.info("No area-specific requests have been recorded.")
with listing_column:
    st.subheader("Most viewed listings")
    if listings:
        listing_frame = pd.DataFrame(listings).set_index("listing_id")
        st.bar_chart(listing_frame["views"])
    else:
        st.info("No listing views have been recorded.")

with st.expander("Token usage"):
    st.write(
        {
            "prompt_tokens": token_usage.get("prompt_tokens", 0),
            "completion_tokens": token_usage.get("completion_tokens", 0),
            "total_tokens": token_usage.get("total_tokens", 0),
        }
    )
