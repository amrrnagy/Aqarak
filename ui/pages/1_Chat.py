"""Bilingual chat page that renders structured API listings as cards."""

from uuid import uuid4

import streamlit as st

from ui.api_client import APIClientError, api_request
from ui.components.listing_card import render_listing_card

st.set_page_config(page_title="Aqarak Chat", layout="wide")
st.title("Chat")

language = st.sidebar.radio(
    "Language",
    options=["en", "ar"],
    format_func=lambda value: "English" if value == "en" else "العربية",
    horizontal=True,
)
if language == "ar":
    st.markdown(
        """
        <style>
        [data-testid="stChatMessage"] { direction: rtl; text-align: right; }
        [data-testid="stChatInput"] textarea { direction: rtl; text-align: right; }
        </style>
        """,
        unsafe_allow_html=True,
    )

if "aqarak_session_id" not in st.session_state:
    st.session_state.aqarak_session_id = str(uuid4())
if "aqarak_chat_history" not in st.session_state:
    st.session_state.aqarak_chat_history = []

st.caption(f"Session: {st.session_state.aqarak_session_id}")

for turn in st.session_state.aqarak_chat_history:
    with st.chat_message("user"):
        st.markdown(turn["message"])
    with st.chat_message("assistant"):
        st.markdown(turn["reply"])
        listings = turn["response"].get("listings", [])
        if listings:
            st.markdown("#### Listings" if language == "en" else "#### العقارات")
            for listing in listings:
                render_listing_card(listing, language)
        sources = turn["response"].get("sources", [])
        if sources:
            with st.expander("Sources" if language == "en" else "المصادر"):
                for source in sources:
                    st.caption(source)

prompt = st.chat_input(
    "Ask about listings, plans, or ROI..."
    if language == "en"
    else "اسأل عن العقارات أو الخطط أو العائد..."
)
if prompt:
    try:
        response = api_request(
            "POST",
            "/v1/chat",
            json={
                "session_id": st.session_state.aqarak_session_id,
                "message": prompt,
                "language": language,
            },
        )
    except APIClientError as exc:
        st.error(str(exc))
    else:
        st.session_state.aqarak_chat_history.append(
            {"message": prompt, "reply": response["reply"], "response": response}
        )
        st.rerun()
