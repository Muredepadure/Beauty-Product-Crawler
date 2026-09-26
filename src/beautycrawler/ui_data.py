"""Pure helpers that shape API data for the Streamlit UI (kept out of the Streamlit
script so they are typed and unit-tested)."""

from decimal import Decimal

from beautycrawler.api.schemas import ProductDetail, ProductHistory, ProductSummary
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
