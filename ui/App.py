"""BeautyCrawler Streamlit UI.

    streamlit run ui/App.py

Talks to the API only through `beautycrawler.ui_client.ApiClient` (base URL from
`BEAUTYCRAWLER_API_BASE_URL`). A product page is addressed as `?product=<id>`, so
product links can be shared.
"""

from html import escape
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from beautycrawler.api.schemas import ProductDetail, ProductSummary
from beautycrawler.ui_client import ApiClient, ApiError, NotFound
from beautycrawler.ui_data import (
    MARKET_BAND_PCT,
    SORT_LABELS,
    active_filter_count,
    card_html,
    empty_hint,
    format_pct,
    history_rows,
    lei_to_bani,
    matrix_rows,
    media_html,
    offer_table_html,
    page_count,
    position_rows,
    product_header_html,
    products_label,
    retailer_rows,
)
from beautycrawler.ui_style import (
    ABOVE_MARKET,
    BELOW_MARKET,
    CSS,
    HEADER_KEY,
    PAGE_ICON,
    PAGE_TITLE,
    TAGLINE,
    header_title,
)

PAGE_SIZE = 24

st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="wide")


@st.cache_resource
def get_client() -> ApiClient:
    return ApiClient()


def open_product(product_id: int) -> None:
    st.query_params["product"] = str(product_id)


def close_product() -> None:
    st.query_params.pop("product", None)


def reset_page() -> None:
    st.session_state["page"] = 1


def header() -> None:
    """Shared CSS and the slim app header shown above every page."""
    st.html(CSS)
    with st.container(key=HEADER_KEY, horizontal=True, gap="small"):
        st.markdown(header_title())
        st.caption(TAGLINE)


# ----------------------------------------------------------------------------- search


def product_card(product: ProductSummary) -> None:
    with st.container(border=True):
        st.markdown(card_html(product), unsafe_allow_html=True)
        st.button(
            "Vezi prețurile",
            key=f"open-{product.id}",
            on_click=open_product,
            args=(product.id,),
            width="stretch",
        )


ALL_BRANDS = "Toate brandurile"
FILTER_DEFAULTS: dict[str, object] = {
    "brand": ALL_BRANDS,
    "category": "",
    "min_lei": 0.0,
    "max_lei": 0.0,
    "in_stock": False,
}


@st.cache_data(ttl=600)
def brand_names() -> list[str]:
    try:
        return [b.name for b in get_client().list_brands(page_size=200).items]
    except ApiError:
        return []


def reset_filters() -> None:
    for key, default in FILTER_DEFAULTS.items():
        st.session_state[key] = default
    reset_page()


def filter_group(title: str) -> None:
    st.markdown(f'<div class="bc-filter-group">{title}</div>', unsafe_allow_html=True)


def search_filters() -> dict[str, Any]:
    """Sidebar filters (P7.3, grouped in P10.3) as `ApiClient.search_products` kwargs."""
    with st.sidebar:
        st.header("Filtre")
        filter_group("Produs")
        brand = st.selectbox(
            "Brand", [ALL_BRANDS, *brand_names()], key="brand", on_change=reset_page
        )
        category = st.text_input(
            "Categorie", key="category", placeholder="ex. Seruri", on_change=reset_page
        )
        filter_group("Preț (lei)")
        low, high = st.columns(2)
        min_lei = low.number_input(
            "De la",
            min_value=0.0,
            step=10.0,
            key="min_lei",
            help="0 înseamnă fără limită",
            on_change=reset_page,
        )
        max_lei = high.number_input(
            "Până la",
            min_value=0.0,
            step=10.0,
            key="max_lei",
            help="0 înseamnă fără limită",
            on_change=reset_page,
        )
        filter_group("Disponibilitate")
        in_stock = st.checkbox("Doar produse în stoc", key="in_stock", on_change=reset_page)
        filters = {
            "brand": None if brand == ALL_BRANDS else brand,
            "category": category or None,
            "min_price_bani": lei_to_bani(min_lei),
            "max_price_bani": lei_to_bani(max_lei),
            "in_stock": in_stock,
        }
        st.button(
            "Resetează filtrele",
            key="reset_filters",
            on_click=reset_filters,
            disabled=not active_filter_count(filters),
            width="stretch",
        )
    return filters


def empty_state(query: str | None, filters: dict[str, Any]) -> None:
    active = active_filter_count(filters)
    st.markdown(
        '<div class="bc-empty"><div class="bc-empty-icon" aria-hidden="true">🔍</div>'
        '<div class="bc-empty-title">Niciun produs găsit</div>'
        f'<div class="bc-empty-hint">{escape(empty_hint(query, active))}</div></div>',
        unsafe_allow_html=True,
    )
    if active:
        with st.container(horizontal=True, horizontal_alignment="center"):
            st.button("Resetează filtrele", key="reset_filters_empty", on_click=reset_filters)


def search_page(api: ApiClient) -> None:
    st.title("🔎 Caută produse")
    q = st.text_input(
        "Caută un produs sau un brand",
        key="q",
        placeholder="Produs sau brand, ex. Effaclar Duo",
        icon=":material/search:",
        label_visibility="collapsed",
        on_change=reset_page,
    )
    filters = search_filters()
    count_col, sort_col = st.columns([3, 1], vertical_alignment="center")
    with sort_col:
        sort = st.selectbox(
            "Sortează",
            options=list(SORT_LABELS),
            format_func=lambda key: SORT_LABELS[key],
            key="sort",
            label_visibility="collapsed",
            on_change=reset_page,
        )
    page = int(st.session_state.get("page", 1))
    try:
        results = api.search_products(
            q or None, sort=sort, page=page, page_size=PAGE_SIZE, **filters
        )
    except ApiError as exc:
        st.error(f"Nu am putut încărca produsele: {exc}")
        return

    if results.total == 0:
        empty_state(q, filters)
        return
    count_col.subheader(products_label(results.total))
    columns = st.columns(3)
    for i, product in enumerate(results.items):
        with columns[i % 3]:
            product_card(product)

    pages = page_count(results.total, PAGE_SIZE)
    if pages > 1:
        st.number_input("Pagina", min_value=1, max_value=pages, step=1, key="page")
        st.caption(f"din {pages}")


# ---------------------------------------------------------------------------- product


HISTORY_PERIODS: dict[str, int | None] = {
    "30 de zile": 30,
    "90 de zile": 90,
    "1 an": 365,
    "Tot istoricul": None,
}


def price_table(product: ProductDetail) -> None:
    if not product.offers:
        st.info("Niciun magazin nu are încă oferte pentru acest produs.")
        return
    st.markdown(offer_table_html(product), unsafe_allow_html=True)


def history_chart(api: ApiClient, product_id: int) -> None:
    st.subheader("Istoricul prețurilor")
    label = st.selectbox("Perioada", options=list(HISTORY_PERIODS), index=1, key="period")
    try:
        history = api.get_history(product_id, days=HISTORY_PERIODS[label])
    except ApiError as exc:
        st.error(f"Nu am putut încărca istoricul: {exc}")
        return
    rows = history_rows(history)
    if not rows:
        st.info("Nu există încă istoric de prețuri.")
        return
    # Colours come from the theme (chartCategoricalColors in .streamlit/config.toml).
    chart = (
        alt.Chart(pd.DataFrame(rows), height=320)
        .mark_line(interpolate="step-after", strokeWidth=2.5, point=alt.OverlayMarkDef(size=36))
        .encode(
            x=alt.X("Data:T", title=None, axis=alt.Axis(format="%d.%m", tickCount=8, grid=False)),
            y=alt.Y("Preț (lei):Q", title="lei", scale=alt.Scale(zero=False)),
            color=alt.Color("Magazin:N", title=None, legend=alt.Legend(orient="bottom")),
            tooltip=["Magazin", alt.Tooltip("Data:T", format="%d.%m.%Y %H:%M"), "Preț (lei)"],
        )
    )
    st.altair_chart(chart, width="stretch")
    st.caption("Prețul se schimbă doar când un magazin îl modifică; golurile = stoc epuizat.")


def product_page(api: ApiClient, product_id: int) -> None:
    st.button("← Înapoi la rezultate", on_click=close_product, type="tertiary")
    try:
        product = api.get_product(product_id)
    except NotFound:
        st.error("Produsul nu există (poate a fost șters).")
        return
    except ApiError as exc:
        st.error(f"Nu am putut încărca produsul: {exc}")
        return
    left, right = st.columns([1, 2], gap="large")
    with left:
        st.markdown(media_html(product), unsafe_allow_html=True)
    with right:
        above, below = product_header_html(product)
        st.markdown(above, unsafe_allow_html=True)
        st.title(product.name)
        st.markdown(below, unsafe_allow_html=True)
    st.subheader("Prețuri în magazine")
    price_table(product)
    history_chart(api, product_id)


# ------------------------------------------------------------------------- competitors


def _pct_color(value: object) -> str:
    """Cell style for % vs median: green below the market, red above."""
    if not isinstance(value, int | float):
        return ""
    if value < -MARKET_BAND_PCT:
        return BELOW_MARKET
    if value > MARKET_BAND_PCT:
        return ABOVE_MARKET
    return ""


def competitors_page(api: ApiClient) -> None:
    st.title("🏷️ Comparație prețuri")
    st.caption(
        "Pentru vânzători: prețul fiecărui magazin față de piață (minimul și mediana "
        "prețurilor în stoc, câte unul per magazin)."
    )
    brands = brand_names()
    if not brands:
        st.info("Nu există încă branduri în baza de date.")
        return
    brand = st.selectbox("Brand", brands, key="cmp_brand")
    try:
        comparison = api.compare(brand)
    except ApiError as exc:
        st.error(f"Nu am putut încărca comparația: {exc}")
        return
    if not comparison.products:
        st.info(f"Niciun produs {brand} nu are încă oferte.")
        return

    st.subheader("Poziția magazinelor")
    st.dataframe(pd.DataFrame(position_rows(comparison)), hide_index=True, width="stretch")

    st.subheader("Față de mediana pieței, pe produs")
    matrix = pd.DataFrame(matrix_rows(comparison))
    stores = [c for c in matrix.columns if c != "Produs"]
    st.dataframe(
        matrix.style.map(_pct_color, subset=stores).format(
            lambda v: format_pct(v) if pd.notna(v) else "—",
            subset=stores,
        ),
        hide_index=True,
        width="stretch",
    )

    slugs = {p.retailer.name: p.retailer.slug for p in comparison.retailers}
    store = st.selectbox("Detalii pentru magazinul", list(slugs), key="cmp_store")
    rows = retailer_rows(comparison, slugs[store])
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    under = sum(r["Poziție"] == "Sub piață" for r in rows)
    over = sum(r["Poziție"] == "Peste piață" for r in rows)
    st.markdown(f"**{store}**: {under} sub piață, {over} peste piață, din {len(rows)} listate.")


# ------------------------------------------------------------------------------- main

PAGES = {"🔎 Caută produse": search_page, "🏷️ Comparație prețuri": competitors_page}


def main() -> None:
    api = get_client()
    header()
    raw_id = st.query_params.get("product")
    if raw_id is not None:
        if raw_id.isdigit():
            product_page(api, int(raw_id))
            return
        close_product()
    with st.sidebar:
        choice = st.radio("Pagina", list(PAGES), key="nav")
    PAGES[choice](api)


main()
