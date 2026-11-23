"""Reusable Streamlit property listing card component."""

from typing import Any, Mapping

import streamlit as st


_TEXT = {
    "en": {
        "price": "Price",
        "area": "Area",
        "bedrooms": "Bedrooms",
        "bathrooms": "Bathrooms",
        "delivery": "Delivery",
        "unavailable": "Not provided",
    },
    "ar": {
        "price": "السعر",
        "area": "المساحة",
        "bedrooms": "غرف النوم",
        "bathrooms": "الحمامات",
        "delivery": "التسليم",
        "unavailable": "غير متاح",
    },
}


def render_listing_card(
    listing: Mapping[str, Any],
    language: str = "en",
) -> None:
    """Render a listing using only fields returned by the API."""
    labels = _TEXT.get(language, _TEXT["en"])
    unavailable = labels["unavailable"]
    with st.container(border=True):
        title_column, type_column = st.columns([3, 1])
        title_column.subheader(listing.get("title") or unavailable)
        if listing.get("property_type"):
            type_column.caption(str(listing["property_type"]))

        location = " · ".join(
            str(value)
            for value in (listing.get("area"), listing.get("city"))
            if value
        )
        st.caption(location or unavailable)
        if listing.get("developer"):
            st.write(str(listing["developer"]))

        price = listing.get("price")
        area = listing.get("area_sqm")
        bedrooms = listing.get("bedrooms")
        bathrooms = listing.get("bathrooms")
        delivery = listing.get("delivery_date")
        columns = st.columns(3)
        columns[0].metric(
            labels["price"],
            f"EGP {price:,.0f}" if isinstance(price, (int, float)) else unavailable,
        )
        columns[1].metric(
            labels["area"],
            f"{area:,.0f} sqm" if isinstance(area, (int, float)) else unavailable,
        )
        bed_value = str(bedrooms) if bedrooms is not None else unavailable
        bath_value = str(bathrooms) if bathrooms is not None else unavailable
        columns[2].metric(
            f'{labels["bedrooms"]} / {labels["bathrooms"]}',
            f"{bed_value} / {bath_value}",
        )
        st.write(
            f'**{labels["delivery"]}:** {delivery or unavailable}'
        )
        if listing.get("description"):
            st.write(str(listing["description"]))
