"""Pure helpers that shape API data for the Streamlit UI (kept out of the Streamlit
script so they are typed and unit-tested)."""

from collections.abc import Mapping
from decimal import Decimal
from html import escape

from beautycrawler.api.schemas import (
    BrandComparison,
    ProductDetail,
    ProductHistory,
    ProductSummary,
)
from beautycrawler.ui_client import format_lei
from beautycrawler.ui_style import ABOVE_MARKET, BELOW_MARKET, GREEN_RGB, RED_RGB

SORT_LABELS: dict[str, str] = {
    "name": "Nume (A-Z)",
    "price_asc": "Preț crescător",
    "price_desc": "Preț descrescător",
    "retailers": "Cele mai multe magazine",
}


def format_size(value: Decimal | None, unit: str | None) -> str:
    """Decimal("40.000"), "ml" -> "40 ml"; missing -> ""."""
    if value is None or not unit:
        return ""
    return f"{value.normalize():f} {unit}".replace(".", ",")


def plural_ro(count: int, one: str, many: str) -> str:
    """Romanian count + noun: 1 produs, 2 produse, 19 produse, 20 de produse, 101 produse."""
    if count == 1:
        return f"1 {one}"
    if count == 0 or 0 < count % 100 < 20:
        return f"{count} {many}"
    return f"{count} de {many}"


def stores_label(count: int) -> str:
    return plural_ro(count, "magazin", "magazine")


def products_label(count: int) -> str:
    return plural_ro(count, "produs", "produse")


PLACEHOLDER_ICON = "💄"


def safe_image_url(url: str | None) -> str | None:
    """Only http(s) image URLs make it into the card markup."""
    if url and url.lower().startswith(("https://", "http://")):
        return url
    return None


def card_badges(product: ProductSummary) -> list[str]:
    badges = []
    if product.on_sale:
        badges.append("Reducere")
    if product.offer_count and not product.in_stock:
        badges.append("Stoc epuizat")
    return badges


def media_html(product: ProductSummary) -> str:
    """The product image in a fixed-ratio white box (placeholder when missing), with
    the card badges on top."""
    image = safe_image_url(product.image_url)
    media = (
        f'<img src="{escape(image)}" alt="{escape(product.name)}" loading="lazy">'
        if image
        else f'<span class="bc-card-placeholder" aria-hidden="true">{PLACEHOLDER_ICON}</span>'
    )
    badges = "".join(
        f'<span class="bc-badge bc-badge-{"sale" if b == "Reducere" else "out"}">{b}</span>'
        for b in card_badges(product)
    )
    return f'<div class="bc-card-media">{media}<div class="bc-card-badges">{badges}</div></div>'


def price_html(product: ProductSummary) -> str:
    """The lowest price, large ("de la" only with several listings), or why none."""
    if product.lowest_price_bani is not None:
        price = format_lei(product.lowest_price_bani)
        if product.offer_count > 1:
            price = f'<span class="bc-from">de la</span> {price}'
        return f'<div class="bc-card-price">{price}</div>'
    missing = "Indisponibil" if product.offer_count else "Fără oferte încă"
    return f'<div class="bc-card-price bc-muted">{missing}</div>'


def stores_line(product: ProductSummary) -> str:
    """ "la 3 magazine", or "" without listings."""
    return f"la {stores_label(product.retailer_count)}" if product.retailer_count else ""


def card_html(product: ProductSummary) -> str:
    """Search result card (P10.2) as one line of HTML for `st.markdown`.

    Every line is always present (an empty one holds a non-breaking space) and the name
    is clamped to two lines by CSS, so cards in a row have the same height. Scraped text
    is escaped. Classes are styled in `ui_style.CSS`.
    """
    name = escape(product.name)
    size = format_size(product.size_value, product.size_unit)
    return (
        '<div class="bc-card">'
        f"{media_html(product)}"
        f'<div class="bc-card-brand">{escape(product.brand or "") or "&nbsp;"}</div>'
        f'<div class="bc-card-name" title="{name}">{name}</div>'
        f'<div class="bc-card-size">{escape(size) or "&nbsp;"}</div>'
        f"{price_html(product)}"
        f'<div class="bc-card-stores">{stores_line(product) or "&nbsp;"}</div>'
        "</div>"
    )


def page_count(total: int, page_size: int) -> int:
    return max(1, -(-total // page_size))


def discount_pct(price_bani: int, old_price_bani: int | None) -> int | None:
    """Whole-percent discount vs the pre-sale price, e.g. 8990 -> 7490 is 17."""
    if not old_price_bani or old_price_bani <= price_bani:
        return None
    return round((old_price_bani - price_bani) * 100 / old_price_bani)


def product_header_html(product: ProductDetail) -> tuple[str, str]:
    """Product page header (P10.4) around the name, which is an `st.title`: the brand
    (small caps) above it; size, price summary and store count below it."""
    brand = escape(product.brand or "")
    size = escape(format_size(product.size_value, product.size_unit))
    above = f'<div class="bc-card-brand bc-detail-brand">{brand or "&nbsp;"}</div>'
    below = (
        f'<div class="bc-detail-meta">{size or "&nbsp;"}</div>'
        f"{price_html(product)}"
        f'<div class="bc-card-stores">{stores_line(product) or "&nbsp;"}</div>'
    )
    return above, below


def offer_table_html(product: ProductDetail) -> str:
    """The product page's price table (P10.4) in the API's order (best first).

    Old prices are struck through with the discount next to them, the cheapest in-stock
    rows are highlighted, and each row links out with a "Vezi în magazin" button (only
    for http(s) URLs). Scraped text is escaped. Rows stack on a phone (CSS).
    """
    rows = []
    for offer in product.offers:
        store = escape(offer.retailer.name)
        if offer.seller_name:
            store += f'<div class="bc-seller">vândut de {escape(offer.seller_name)}</div>'
        if offer.is_cheapest:
            store += '<div class="bc-best">Cel mai mic preț</div>'
        price = f'<span class="bc-offer-price">{format_lei(offer.price_bani)}</span>'
        discount = discount_pct(offer.price_bani, offer.old_price_bani)
        if discount and offer.old_price_bani:
            price += (
                f' <s class="bc-old-price">{format_lei(offer.old_price_bani)}</s>'
                f' <span class="bc-discount">-{discount}%</span>'
            )
        stock = (
            '<span class="bc-stock bc-in-stock">În stoc</span>'
            if offer.in_stock
            else '<span class="bc-stock bc-out-of-stock">Stoc epuizat</span>'
        )
        url = safe_image_url(offer.url)  # same rule: http(s) only
        link = (
            f'<a class="bc-shop-btn" href="{escape(url)}" target="_blank" '
            'rel="noopener noreferrer nofollow">Vezi în magazin</a>'
            if url
            else ""
        )
        row_class = ' class="bc-cheapest"' if offer.is_cheapest else ""
        rows.append(
            f"<tr{row_class}>"
            f'<td class="bc-col-store">{store}</td>'
            f'<td class="bc-col-price">{price}</td>'
            f'<td class="bc-col-stock">{stock}</td>'
            f'<td class="bc-col-link">{link}</td>'
            "</tr>"
        )
    return (
        '<div class="bc-offers"><table>'
        "<thead><tr><th>Magazin</th><th>Preț</th><th>Stoc</th><th></th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def history_rows(history: ProductHistory) -> list[dict[str, object]]:
    """Chart rows (store, time, price in lei; None while out of stock).

    Each series is extended to its `last_seen_at`, so a price that hasn't changed for
    weeks is drawn up to the last crawl instead of stopping at its first observation.
    """
    rows: list[dict[str, object]] = []
    for series in history.series:
        store = series.retailer.name
        if series.seller_name:
            store += f" ({series.seller_name})"
        for point in series.points:
            rows.append(
                {
                    "Magazin": store,
                    "Data": point.scraped_at,
                    "Preț (lei)": point.price_bani / 100 if point.in_stock else None,
                }
            )
        if series.points and series.last_seen_at > series.points[-1].scraped_at:
            last = dict(rows[-1])
            last["Data"] = series.last_seen_at
            rows.append(last)
    return rows


def active_filter_count(filters: Mapping[str, object]) -> int:
    """How many search filters are set (`ApiClient.search_products` kwargs; None, False
    and "" mean "not set")."""
    # `is` checks: 0 == False, but a 0 bani bound is still a filter.
    return sum(1 for v in filters.values() if v is not None and v is not False and v != "")


def empty_hint(query: str | None, active_filters: int) -> str:
    """What to try next when a search finds nothing."""
    if active_filters:
        return "Încearcă mai puține filtre sau alt termen de căutare."
    if query and query.strip():
        return "Verifică ortografia sau caută doar după brand (ex. „CeraVe”)."
    return "Încă nu există produse în catalog."


def lei_to_bani(lei: float | None) -> int | None:
    """A price typed in lei (0 or empty = no limit) as integer bani."""
    if not lei or lei <= 0:
        return None
    return round(lei * 100)


# --- P7.4 competitor view ------------------------------------------------------------

MARKET_BAND_PCT = 2.0  # within ±2 % of the median counts as "at market"


def format_pct(pct: float | None) -> str:
    """+11.1 -> "+11,1%"; -5.0 -> "-5,0%"; None -> "—"."""
    if pct is None:
        return "—"
    return f"{pct:+.1f}%".replace(".", ",")


def market_position(pct_vs_median: float | None, in_stock: bool) -> str:
    if not in_stock:
        return "Stoc epuizat"
    if pct_vs_median is None:
        return "—"
    if pct_vs_median < -MARKET_BAND_PCT:
        return "Sub piață"
    if pct_vs_median > MARKET_BAND_PCT:
        return "Peste piață"
    return "La nivelul pieței"


MARKET_CLASS = {"Sub piață": "bc-below", "Peste piață": "bc-above"}

MARKET_LEGEND_HTML = (
    '<div class="bc-legend">'
    '<span class="bc-pill bc-below">Sub mediană: mai ieftin decât piața</span>'
    f'<span class="bc-pill">La nivelul pieței (±{MARKET_BAND_PCT:.0f}%)</span>'
    '<span class="bc-pill bc-above">Peste mediană: mai scump</span>'
    "</div>"
)


def pct_cell_style(value: object) -> str:
    """Heatmap cell for % vs median: green below, red above, stronger the further from
    the median (full strength at ±20 %); no colour within the ±2 % band or when empty."""
    if not isinstance(value, int | float) or value != value:  # NaN
        return ""
    if abs(value) <= MARKET_BAND_PCT:
        return ""
    alpha = 0.12 + 0.33 * min(abs(value), 20.0) / 20.0
    rgb = GREEN_RGB if value < 0 else RED_RGB
    return f"background-color: rgba({rgb}, {alpha:.2f})"


def position_style(label: object) -> str:
    """Cell style for the "Poziție" column of the store detail table."""
    return {"Sub piață": BELOW_MARKET, "Peste piață": ABOVE_MARKET}.get(str(label), "")


def position_cards_html(comparison: BrandComparison) -> str:
    """One card per retailer: average % vs the median as a coloured pill, and on how many
    of its listed products it is the cheapest."""
    cards = []
    for p in comparison.retailers:
        label = market_position(p.avg_vs_median_pct, True)
        css = MARKET_CLASS.get(label, "")
        pill = f'<span class="bc-pill{" " + css if css else ""}">'
        listed = plural_ro(p.products_listed, "produs", "produse")
        cards.append(
            '<div class="bc-stat">'
            f'<div class="bc-stat-store">{escape(p.retailer.name)}</div>'
            f'<div class="bc-stat-value">{pill}{format_pct(p.avg_vs_median_pct)}</span></div>'
            '<div class="bc-stat-label">față de mediană, în medie</div>'
            f'<div class="bc-stat-foot">cel mai ieftin la {p.cheapest_count} din {listed}</div>'
            "</div>"
        )
    return f'<div class="bc-stats">{"".join(cards)}</div>'


def retailer_rows(comparison: BrandComparison, retailer_slug: str) -> list[dict[str, object]]:
    """The retailer's price for each of the brand's products it lists, vs the market."""
    rows: list[dict[str, object]] = []
    for product in comparison.products:
        mine = next((p for p in product.prices if p.retailer.slug == retailer_slug), None)
        if mine is None:
            continue
        rows.append(
            {
                "Produs": product.name,
                "Mărime": format_size(product.size_value, product.size_unit),
                "Prețul magazinului": format_lei(mine.price_bani),
                "Minim piață": format_lei(product.market_min_bani),
                "Median piață": format_lei(product.market_median_bani),
                "Față de median": format_pct(mine.vs_median_pct),
                "Poziție": market_position(mine.vs_median_pct, mine.in_stock),
            }
        )
    return rows


def matrix_rows(comparison: BrandComparison) -> list[dict[str, object]]:
    """Product-by-retailer grid of % vs the median (None where not listed / no market)."""
    names = [p.retailer.name for p in comparison.retailers]
    rows: list[dict[str, object]] = []
    for product in comparison.products:
        row: dict[str, object] = {"Produs": product.name, **dict.fromkeys(names)}
        for price in product.prices:
            row[price.retailer.name] = price.vs_median_pct
        rows.append(row)
    return rows
