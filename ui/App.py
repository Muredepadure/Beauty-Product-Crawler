"""BeautyCrawler Streamlit UI.

    streamlit run ui/App.py

Talks to the API only through `beautycrawler.ui_client.ApiClient` (base URL from
`BEAUTYCRAWLER_API_BASE_URL`). A product page is addressed as `?product=<id>`, so
product links can be shared.
"""

import altair as alt
import pandas as pd
import streamlit as st

from beautycrawler.api.schemas import ProductDetail, ProductSummary
from beautycrawler.ui_client import ApiClient, ApiError, NotFound
from beautycrawler.ui_data import (
    SORT_LABELS,
    card_price_line,
    card_subtitle,
    history_rows,
    offer_rows,
    page_count,
    products_label,
)

PAGE_SIZE = 24

st.set_page_config(page_title="BeautyCrawler — prețuri cosmetice", page_icon="💄", layout="wide")


@st.cache_resource
def get_client() -> ApiClient:
    return ApiClient()


def open_product(product_id: int) -> None:
    st.query_params["product"] = str(product_id)


def close_product() -> None:
    st.query_params.pop("product", None)


def reset_page() -> None:
    st.session_state["page"] = 1


# ----------------------------------------------------------------------------- search


def product_card(product: ProductSummary) -> None:
    with st.container(border=True):
        if product.image_url:
            st.image(product.image_url, width="stretch")
        st.markdown(f"**{product.name}**")
        subtitle = card_subtitle(product)
        if subtitle:
            st.caption(subtitle)
        st.markdown(card_price_line(product))
        st.button(
            "Vezi prețurile",
            key=f"open-{product.id}",
            on_click=open_product,
            args=(product.id,),
            width="stretch",
        )


def search_page(api: ApiClient) -> None:
    st.title("🔎 Caută produse")
    st.caption("Compară prețurile produselor cosmetice în magazinele online din România.")
    q = st.text_input(
        "Produs sau brand",
        key="q",
        placeholder="ex. Effaclar Duo, CeraVe, ser cu vitamina C",
        on_change=reset_page,
    )
    sort = st.selectbox(
        "Sortează",
        options=list(SORT_LABELS),
        format_func=lambda key: SORT_LABELS[key],
        key="sort",
        on_change=reset_page,
    )
    page = int(st.session_state.get("page", 1))
    try:
        results = api.search_products(q or None, sort=sort, page=page, page_size=PAGE_SIZE)
    except ApiError as exc:
        st.error(f"Nu am putut încărca produsele: {exc}")
        return

    if results.total == 0:
        st.info("Niciun produs găsit. Încearcă alt termen de căutare.")
        return
    st.subheader(products_label(results.total))
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
    rows = offer_rows(product)
    if not rows:
        st.info("Niciun magazin nu are încă oferte pentru acest produs.")
        return
    frame = pd.DataFrame(rows)
    cheapest = [bool(r[""]) for r in rows]

    def highlight(row: pd.Series) -> list[str]:
        style = "background-color: rgba(46, 160, 67, 0.18)" if cheapest[row.name] else ""
        return [style] * len(row)

    st.dataframe(
        frame.style.apply(highlight, axis=1),
        hide_index=True,
        width="stretch",
        column_config={
            "": st.column_config.TextColumn("", width="small"),
            "Link": st.column_config.LinkColumn("Link", display_text="Deschide ↗"),
        },
    )


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
    chart = (
        alt.Chart(pd.DataFrame(rows))
        .mark_line(interpolate="step-after", point=True)
        .encode(
            x=alt.X("Data:T", title=None),
            y=alt.Y("Preț (lei):Q", scale=alt.Scale(zero=False)),
            color=alt.Color("Magazin:N", title="Magazin"),
            tooltip=["Magazin", alt.Tooltip("Data:T", format="%d.%m.%Y %H:%M"), "Preț (lei)"],
        )
    )
    st.altair_chart(chart, width="stretch")
    st.caption("Prețul se schimbă doar când un magazin îl modifică; golurile = stoc epuizat.")


def product_page(api: ApiClient, product_id: int) -> None:
    st.button("← Înapoi la căutare", on_click=close_product)
    try:
        product = api.get_product(product_id)
    except NotFound:
        st.error("Produsul nu există (poate a fost șters).")
        return
    except ApiError as exc:
        st.error(f"Nu am putut încărca produsul: {exc}")
        return
    left, right = st.columns([1, 3])
    with left:
        if product.image_url:
            st.image(product.image_url, width="stretch")
    with right:
        st.title(product.name)
        subtitle = card_subtitle(product)
        if subtitle:
            st.caption(subtitle)
        st.markdown(card_price_line(product))
    price_table(product)
    history_chart(api, product_id)


# ------------------------------------------------------------------------------- main


def main() -> None:
    api = get_client()
    raw_id = st.query_params.get("product")
    if raw_id is not None:
        if raw_id.isdigit():
            product_page(api, int(raw_id))
            return
        close_product()
    search_page(api)


main()
