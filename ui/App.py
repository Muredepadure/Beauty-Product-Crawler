"""BeautyCrawler Streamlit UI.

    streamlit run ui/App.py

Talks to the API only through `beautycrawler.ui_client.ApiClient` (base URL from
`BEAUTYCRAWLER_API_BASE_URL`). A product page is addressed as `?product=<id>`, so
product links can be shared.

The URL is the source of truth for the search (P12.1): the search text, filters, sort
and page are kept in the query parameters (`?q=…&brand=…&page=2`) next to `product`.
Streamlit pushes a browser history entry whenever the script changes `st.query_params`;
it doesn't rerun when the back/forward arrows change the URL, so a small script reloads
the page then (`BACK_FORWARD_JS`, P13.2). The arrows move between result pages and
product pages, and every results URL can be shared.
"""

from html import escape
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from beautycrawler.api.schemas import ProductDetail, ProductSummary
from beautycrawler.config import get_settings
from beautycrawler.normalization.text import fold
from beautycrawler.ui_client import ApiClient, ApiError, NotFound
from beautycrawler.ui_data import (
    MARKET_LEGEND_HTML,
    SEARCH_DEFAULTS,
    SEARCH_URL_KEYS,
    SORT_LABELS,
    active_filter_count,
    api_error_message,
    card_html,
    common_caption,
    common_hint,
    empty_hint,
    format_pct,
    freshness_text,
    history_rows,
    lei_to_bani,
    matrix_rows,
    media_html,
    offer_table_html,
    page_count,
    pct_cell_style,
    position_cards_html,
    position_style,
    product_header_html,
    products_label,
    retailer_rows,
    search_state_from_params,
    search_state_to_params,
)
from beautycrawler.ui_style import (
    CSS,
    HEADER_KEY,
    PAGE_ICON,
    PAGE_TITLE,
    TAGLINE,
    header_title,
)

PAGE_SIZE = 24

FAVICON = Path(__file__).with_name("favicon.png")

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=str(FAVICON) if FAVICON.exists() else PAGE_ICON,
    layout="wide",
)


@st.cache_resource
def get_client() -> ApiClient:
    return ApiClient()


def open_product(product_id: int) -> None:
    st.query_params["product"] = str(product_id)


def close_product() -> None:
    st.query_params.pop("product", None)


def reset_page() -> None:
    st.session_state["page"] = 1


# ------------------------------------------------------------------ search state in URL

URL_SYNCED = "_search_url"  # the search params the widgets were last loaded from/saved to


def search_params_in_url() -> dict[str, str]:
    names = set(SEARCH_URL_KEYS.values())
    return {k: v for k, v in st.query_params.to_dict().items() if k in names}


def load_search_from_url() -> None:
    """Set the search widgets from the URL when it was changed outside the search page
    (first load, a shared link, the back/forward arrows, coming back from a product).

    While the user works the widgets, the URL equals what this page last wrote, so the
    widgets' own state wins and `save_search_to_url` updates the URL after them.
    """
    in_url = search_params_in_url()
    if st.session_state.get(URL_SYNCED) == in_url:
        return
    state = search_state_from_params(in_url)
    state["brand"] = state["brand"] or ALL_BRANDS
    state["category"] = state["category"] or ALL_CATEGORIES
    state["retailers"] = list(state["retailers"])  # the multiselect wants a list
    for key, value in state.items():
        st.session_state[key] = value
    st.session_state[URL_SYNCED] = in_url


def search_state() -> dict[str, object]:
    state = {key: st.session_state.get(key, default) for key, default in SEARCH_DEFAULTS.items()}
    if state["brand"] == ALL_BRANDS:
        state["brand"] = ""
    if state["category"] == ALL_CATEGORIES:
        state["category"] = ""
    return state


def save_search_to_url() -> None:
    """Write the current search into the URL (one history entry per change); other
    parameters are kept."""
    wanted = search_state_to_params(search_state())
    if wanted != search_params_in_url():
        others = {
            k: v for k, v in st.query_params.to_dict().items() if k not in SEARCH_URL_KEYS.values()
        }
        st.query_params.from_dict({**others, **wanted})
    st.session_state[URL_SYNCED] = wanted


def forget_search_widgets() -> None:
    """Off the search page Streamlit drops the search widgets' state, so the next visit
    reloads it from the URL."""
    st.session_state.pop(URL_SYNCED, None)


def show_api_error(exc: ApiError, what: str) -> None:
    st.error(api_error_message(exc, what, get_settings().api_base_url))


@st.cache_data(ttl=300)
def freshness() -> str | None:
    try:
        return freshness_text(get_client().list_retailers())
    except ApiError:
        return None  # the page itself already says the API is down


def footer() -> None:
    text = freshness()
    if text:
        st.markdown(f'<div class="bc-footer">{escape(text)}</div>', unsafe_allow_html=True)


# Streamlit adds a history entry when the script changes `st.query_params`, but it does
# not rerun when the browser's back/forward arrows change the URL: the address changes
# and the page stays. The URL holds the whole state, so reloading it is enough. Added once
# per tab (the flag survives reruns, which re-render this element).
BACK_FORWARD_JS = """<script>
if (!window.__bcBackForward) {
  window.__bcBackForward = true;
  window.addEventListener("popstate", () => window.location.reload());
}
</script>"""


def header() -> None:
    """Shared CSS and the slim app header shown above every page."""
    st.html(CSS)
    st.html(BACK_FORWARD_JS, unsafe_allow_javascript=True)
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
ALL_CATEGORIES = "Toate categoriile"
FILTER_DEFAULTS: dict[str, object] = {
    "brand": ALL_BRANDS,
    "category": ALL_CATEGORIES,
    "min_lei": 0.0,
    "max_lei": 0.0,
    "in_stock": False,
    "retailers": (),
    "common": False,
}


@st.cache_data(ttl=600)
def brand_names() -> list[str]:
    """Every brand with listed products (all pages: there are hundreds)."""
    try:
        return get_client().all_brand_names(unlisted="auto")
    except ApiError:
        return []


@st.cache_data(ttl=600)
def category_counts() -> dict[str, int]:
    """Category -> number of listed products, in the categories' display order."""
    try:
        return {c.name: c.product_count for c in get_client().list_categories(unlisted="auto")}
    except ApiError:
        return {}


@st.cache_data(ttl=600)
def shop_names() -> dict[str, str]:
    """Slug -> name of the retailers that have listed products, by name."""
    try:
        retailers = get_client().list_retailers()
    except ApiError:
        return {}
    return {
        r.slug: r.name
        for r in sorted(retailers, key=lambda r: r.name.casefold())
        if r.product_count
    }


def common_changed() -> None:
    """Most shops first while "Doar produse comune" is on, unless another sort was chosen."""
    reset_page()
    sort = st.session_state.get("sort", "name")
    if st.session_state.get("common") and sort == "name":
        st.session_state["sort"] = "retailers"
    elif not st.session_state.get("common") and sort == "retailers":
        st.session_state["sort"] = "name"


def reset_filters() -> None:
    for key, default in FILTER_DEFAULTS.items():
        st.session_state[key] = list(default) if isinstance(default, tuple) else default
    reset_page()


def filter_group(title: str) -> None:
    st.markdown(f'<div class="bc-filter-group">{title}</div>', unsafe_allow_html=True)


def search_filters() -> dict[str, Any]:
    """Sidebar filters (P7.3, grouped in P10.3) as `ApiClient.search_products` kwargs."""
    with st.sidebar:
        st.header("Filtre")
        filter_group("Produs")
        brands = [ALL_BRANDS, *brand_names()]
        if st.session_state.get("brand") not in brands:  # e.g. an old link
            st.session_state["brand"] = ALL_BRANDS
        brand = st.selectbox("Brand", brands, key="brand", on_change=reset_page)
        counts = category_counts()
        categories = [ALL_CATEGORIES, *counts]
        if st.session_state.get("category") not in categories:  # e.g. an old link
            by_key = {fold(c): c for c in categories}
            wanted = fold(str(st.session_state.get("category") or ""))
            st.session_state["category"] = by_key.get(wanted, ALL_CATEGORIES)
        category = st.selectbox(
            "Categorie",
            categories,
            key="category",
            format_func=lambda c: f"{c} ({counts[c]})" if c in counts else c,
            on_change=reset_page,
        )
        filter_group("Magazine")
        shops = shop_names()
        chosen = st.session_state.get("retailers") or []
        if any(slug not in shops for slug in chosen):  # e.g. an old link
            st.session_state["retailers"] = [slug for slug in chosen if slug in shops]
        retailers = st.multiselect(
            "Magazine",
            list(shops),
            format_func=lambda slug: shops.get(slug, slug),
            key="retailers",
            placeholder="Toate magazinele",
            label_visibility="collapsed",
            on_change=reset_page,
        )
        common = st.toggle(
            "Doar produse comune",
            key="common",
            help="Cu magazine alese: doar produsele vândute în toate. "
            "Fără magazine alese: doar produsele vândute în cel puțin 2 magazine.",
            on_change=common_changed,
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
            "category": None if category == ALL_CATEGORIES else category,
            "min_price_bani": lei_to_bani(min_lei),
            "max_price_bani": lei_to_bani(max_lei),
            "in_stock": in_stock,
            "retailers": retailers or None,
            "common": common,
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
    hint = empty_hint(query, active)
    if filters.get("common"):
        hint = common_hint(len(filters.get("retailers") or ())) or hint
    st.markdown(
        '<div class="bc-empty"><div class="bc-empty-icon" aria-hidden="true">🔍</div>'
        '<div class="bc-empty-title">Niciun produs găsit</div>'
        f'<div class="bc-empty-hint">{escape(hint)}</div></div>',
        unsafe_allow_html=True,
    )
    if active:
        with st.container(horizontal=True, horizontal_alignment="center"):
            st.button("Resetează filtrele", key="reset_filters_empty", on_click=reset_filters)


def search_page(api: ApiClient) -> None:
    load_search_from_url()
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
    save_search_to_url()
    try:
        with st.spinner("Se încarcă produsele…"):
            # "auto": the seed's demo products vanish once real offers exist (P10.7).
            results = api.search_products(
                q or None, sort=sort, page=page, page_size=PAGE_SIZE, unlisted="auto", **filters
            )
    except ApiError as exc:
        show_api_error(exc, "produsele")
        return

    if results.total == 0:
        empty_state(q, filters)
        return
    count_col.subheader(products_label(results.total))
    if filters["common"] and (caption := common_caption(len(filters["retailers"] or ()))):
        count_col.caption(caption)
    columns = st.columns(3)
    for i, product in enumerate(results.items):
        with columns[i % 3]:
            product_card(product)

    pages = page_count(results.total, PAGE_SIZE)
    if page > pages:  # e.g. an old link, now that there are fewer results
        st.session_state["page"] = pages
        st.rerun()
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
        with st.spinner("Se încarcă istoricul…"):
            history = api.get_history(product_id, days=HISTORY_PERIODS[label])
    except ApiError as exc:
        show_api_error(exc, "istoricul prețurilor")
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
            tooltip=["Magazin", alt.Tooltip("Data:T", format="%d.%m.%Y %H:%M"), "Preț"],
        )
    )
    st.altair_chart(chart, width="stretch")
    st.caption("Prețul se schimbă doar când un magazin îl modifică; golurile = stoc epuizat.")


def product_page(api: ApiClient, product_id: int) -> None:
    st.button("← Înapoi la rezultate", on_click=close_product, type="tertiary")
    try:
        with st.spinner("Se încarcă produsul…"):
            product = api.get_product(product_id)
    except NotFound:
        st.error("Produsul nu există (poate a fost șters).")
        return
    except ApiError as exc:
        show_api_error(exc, "produsul")
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


def competitors_page(api: ApiClient) -> None:
    st.title("🏷️ Comparație prețuri")
    st.markdown(
        "Pentru vânzători: cum se poziționează fiecare magazin față de piață la produsele "
        "unui brand. **Mediana** este prețul din mijloc dintre magazinele care au produsul "
        "în stoc (câte un preț per magazin)."
    )
    brands = brand_names()
    if not brands:
        st.info("Nu există încă branduri în baza de date.")
        return
    brand = st.selectbox("Brand", brands, key="cmp_brand")
    try:
        with st.spinner("Se calculează comparația…"):
            comparison = api.compare(brand)
    except ApiError as exc:
        show_api_error(exc, "comparația")
        return
    if not comparison.products:
        st.info(f"Niciun produs {brand} nu are încă oferte.")
        return

    st.subheader("Poziția magazinelor")
    st.markdown(position_cards_html(comparison), unsafe_allow_html=True)

    st.subheader("Față de mediana pieței, pe produs")
    st.markdown(MARKET_LEGEND_HTML, unsafe_allow_html=True)
    values = pd.DataFrame(matrix_rows(comparison))
    stores = [c for c in values.columns if c != "Produs"]
    # The grid shows a missing number as "None" whatever the formatter, so it gets the
    # display strings; the colours still come from the numbers.
    shown = values.copy()
    shown[stores] = values[stores].map(lambda v: format_pct(v) if pd.notna(v) else "—")
    st.dataframe(
        shown.style.apply(lambda col: [pct_cell_style(v) for v in values[col.name]], subset=stores),
        hide_index=True,
        width="stretch",
        column_config={s: st.column_config.TextColumn(s) for s in stores},
    )
    st.caption("— = magazinul nu listează produsul sau nu există încă un preț de piață.")

    st.subheader("Detalii pe magazin")
    slugs = {p.retailer.name: p.retailer.slug for p in comparison.retailers}
    store = st.selectbox("Magazin", list(slugs), key="cmp_store")
    rows = retailer_rows(comparison, slugs[store])
    st.dataframe(
        pd.DataFrame(rows).style.map(position_style, subset=["Poziție"]),
        hide_index=True,
        width="stretch",
    )
    under = sum(r["Poziție"] == "Sub piață" for r in rows)
    over = sum(r["Poziție"] == "Peste piață" for r in rows)
    st.markdown(f"**{store}**: {under} sub piață, {over} peste piață, din {len(rows)} listate.")


# ------------------------------------------------------------------------------- main

PAGES = {"🔎 Caută produse": search_page, "🏷️ Comparație prețuri": competitors_page}


def main() -> None:
    api = get_client()
    header()
    raw_id = st.query_params.get("product")
    if raw_id is not None and not raw_id.isdigit():
        close_product()
        raw_id = None
    if raw_id is not None:
        forget_search_widgets()
        product_page(api, int(raw_id))
    else:
        with st.sidebar:
            choice = st.radio("Pagina", list(PAGES), key="nav")
        if PAGES[choice] is not search_page:
            forget_search_widgets()
        PAGES[choice](api)
    footer()


main()
