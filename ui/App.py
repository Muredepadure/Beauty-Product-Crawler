import httpx
import streamlit as st

API_BASE = "http://localhost:8000/api"

st.set_page_config(page_title="Beauty Product Search", layout="wide")
st.title("🔎 Beauty Product Search")

q = st.text_input("Search by product or brand", placeholder="e.g., serum, lipstick, PureSkin")
col1, col2, col3 = st.columns(3)
with col1:
    brand = st.text_input("Brand (optional)")
with col2:
    category = st.text_input("Category (optional)")
with col3:
    limit = st.number_input("Results per page", min_value=1, max_value=100, value=24, step=1)

if st.button("Search") or q or brand or category:
    params = {"q": q or None, "brand": brand or None, "category": category or None, "limit": int(limit)}
    with httpx.Client(timeout=15.0) as client:
        r = client.get(f"{API_BASE}/products", params=params)
        r.raise_for_status()
        data = r.json()

    st.subheader(f"Results ({data['total']})")
    items = data["items"]
    cols = st.columns(3)
    for i, p in enumerate(items):
        with cols[i % 3]:
            st.image(p.get("image_url"), use_column_width=True)
            st.markdown(f"**{p['name']}**")
            st.caption(f"{p['brand']} • {p.get('category','')}")
            st.markdown(f"**{p['price']} {p['currency']}**")
            st.link_button("Go to provider", p["provider"])
