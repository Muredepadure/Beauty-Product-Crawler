"""Pure helpers that shape API data for the Streamlit UI (kept out of the Streamlit
script so they are typed and unit-tested)."""

from decimal import Decimal
from html import escape

from beautycrawler.api.schemas import (
    BrandComparison,
    ProductDetail,
    ProductHistory,
    ProductSummary,
)
from beautycrawler.ui_client import format_lei

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


def card_price_line(product: ProductSummary) -> str:
    """E.g. "de la 69,90 lei · 3 magazine", or why there's no price."""
    stores = stores_label(product.retailer_count)
    if product.lowest_price_bani is not None:
        return f"de la {format_lei(product.lowest_price_bani)} · {stores}"
    if product.offer_count:
        return f"Stoc epuizat · {stores}"
    return "Fără oferte încă"


def card_subtitle(product: ProductSummary) -> str:
    parts = [product.brand or "", format_size(product.size_value, product.size_unit)]
    return " · ".join(p for p in parts if p)


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


def card_html(product: ProductSummary) -> str:
    """Search result card (P10.2) as one line of HTML for `st.markdown`.

    Every line is always present (an empty one holds a non-breaking space) and the name
    is clamped to two lines by CSS, so cards in a row have the same height. Scraped text
    is escaped. Classes are styled in `ui_style.CSS`.
    """
    name = escape(product.name)
    image = safe_image_url(product.image_url)
    media = (
        f'<img src="{escape(image)}" alt="{name}" loading="lazy">'
        if image
        else f'<span class="bc-card-placeholder" aria-hidden="true">{PLACEHOLDER_ICON}</span>'
    )
    badges = "".join(
        f'<span class="bc-badge bc-badge-{"sale" if b == "Reducere" else "out"}">{b}</span>'
        for b in card_badges(product)
    )
    if product.lowest_price_bani is not None:
        price = format_lei(product.lowest_price_bani)
        if product.offer_count > 1:
            price = f'<span class="bc-from">de la</span> {price}'
        price_line = f'<div class="bc-card-price">{price}</div>'
    else:
        missing = "Indisponibil" if product.offer_count else "Fără oferte încă"
        price_line = f'<div class="bc-card-price bc-muted">{missing}</div>'
    stores = f"la {stores_label(product.retailer_count)}" if product.retailer_count else ""
    size = format_size(product.size_value, product.size_unit)
    return (
        '<div class="bc-card">'
        f'<div class="bc-card-media">{media}<div class="bc-card-badges">{badges}</div></div>'
        f'<div class="bc-card-brand">{escape(product.brand or "") or "&nbsp;"}</div>'
        f'<div class="bc-card-name" title="{name}">{name}</div>'
        f'<div class="bc-card-size">{escape(size) or "&nbsp;"}</div>'
        f"{price_line}"
        f'<div class="bc-card-stores">{stores or "&nbsp;"}</div>'
        "</div>"
    )


def page_count(total: int, page_size: int) -> int:
    return max(1, -(-total // page_size))


def discount_pct(price_bani: int, old_price_bani: int | None) -> int | None:
    """Whole-percent discount vs the pre-sale price, e.g. 8990 -> 7490 is 17."""
    if not old_price_bani or old_price_bani <= price_bani:
        return None
    return round((old_price_bani - price_bani) * 100 / old_price_bani)


def offer_rows(product: ProductDetail) -> list[dict[str, object]]:
    """Rows for the product page's price table, in the API's order (best first)."""
    rows: list[dict[str, object]] = []
    for offer in product.offers:
        store = offer.retailer.name
        if offer.seller_name:
            store += f" (vândut de {offer.seller_name})"
        discount = discount_pct(offer.price_bani, offer.old_price_bani)
        rows.append(
            {
                "": "🏆" if offer.is_cheapest else "",
                "Magazin": store,
                "Preț": format_lei(offer.price_bani),
                "Preț vechi": format_lei(offer.old_price_bani) if offer.old_price_bani else "",
                "Reducere": f"-{discount}%" if discount else "",
                "Stoc": "În stoc" if offer.in_stock else "Stoc epuizat",
                "Link": offer.url,
            }
        )
    return rows


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


def position_rows(comparison: BrandComparison) -> list[dict[str, object]]:
    return [
        {
            "Magazin": p.retailer.name,
            "Produse listate": p.products_listed,
            "Cel mai ieftin la": p.cheapest_count,
            "Medie față de median": format_pct(p.avg_vs_median_pct),
        }
        for p in comparison.retailers
    ]


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
