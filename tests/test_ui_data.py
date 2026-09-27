import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from beautycrawler.api.schemas import (
    BrandComparison,
    ProductDetail,
    ProductHistory,
    ProductSummary,
)
from beautycrawler.ui_data import (
    MARKET_LEGEND_HTML,
    active_filter_count,
    card_badges,
    card_html,
    discount_pct,
    empty_hint,
    format_pct,
    format_size,
    history_rows,
    lei_to_bani,
    market_position,
    matrix_rows,
    media_html,
    offer_table_html,
    page_count,
    pct_cell_style,
    plural_ro,
    position_cards_html,
    position_style,
    price_html,
    product_header_html,
    products_label,
    retailer_rows,
    safe_image_url,
    stores_label,
    stores_line,
)


@pytest.mark.parametrize(
    ("count", "text"),
    [
        (0, "0 produse"),
        (1, "1 produs"),
        (2, "2 produse"),
        (19, "19 produse"),
        (20, "20 de produse"),
        (101, "101 produse"),
        (119, "119 produse"),
        (120, "120 de produse"),
    ],
)
def test_products_label(count: int, text: str) -> None:
    assert products_label(count) == text


def test_stores_label_and_plural() -> None:
    assert (stores_label(1), stores_label(3), stores_label(25)) == (
        "1 magazin",
        "3 magazine",
        "25 de magazine",
    )
    assert plural_ro(21, "leu", "lei") == "21 de lei"


@pytest.mark.parametrize(
    ("value", "unit", "text"),
    [
        (Decimal("40.000"), "ml", "40 ml"),
        (Decimal("1.5"), "l", "1,5 l"),
        (Decimal("0.250"), "kg", "0,25 kg"),
        (None, "ml", ""),
        (Decimal(1), None, ""),
    ],
)
def test_format_size(value: Decimal | None, unit: str | None, text: str) -> None:
    assert format_size(value, unit) == text


def _summary(**kw: object) -> ProductSummary:
    base: dict[str, object] = {
        "id": 1,
        "name": "Effaclar Duo+",
        "brand": "La Roche-Posay",
        "category": None,
        "size_value": Decimal(40),
        "size_unit": "ml",
        "ean": None,
        "image_url": None,
        "lowest_price_bani": 7_450,
        "offer_count": 3,
        "retailer_count": 2,
        "in_stock": True,
    }
    return ProductSummary.model_validate(base | kw)


def test_price_html_and_stores_line() -> None:
    assert price_html(_summary()) == (
        '<div class="bc-card-price"><span class="bc-from">de la</span> 74,50 lei</div>'
    )
    assert stores_line(_summary()) == "la 2 magazine"
    assert stores_line(_summary(retailer_count=0, offer_count=0)) == ""


# --- P10.3: search filters and empty state --------------------------------------------


def test_active_filter_count() -> None:
    none = {"brand": None, "category": None, "min_price_bani": None, "in_stock": False}
    assert active_filter_count(none) == 0
    assert active_filter_count(none | {"brand": "CeraVe", "in_stock": True}) == 2
    assert active_filter_count(none | {"category": "", "min_price_bani": 0}) == 1  # 0 is set


def test_empty_hint() -> None:
    assert empty_hint("cerave", 1).startswith("Încearcă mai puține filtre")
    assert empty_hint(None, 2).startswith("Încearcă mai puține filtre")
    assert empty_hint("cerve", 0).startswith("Verifică ortografia")
    assert empty_hint("   ", 0) == "Încă nu există produse în catalog."
    assert empty_hint(None, 0) == "Încă nu există produse în catalog."


# --- P10.2: search result cards --------------------------------------------------------


def test_card_html_in_stock() -> None:
    html = card_html(_summary(image_url="https://cdn.test/duo.jpg"))
    assert html.startswith('<div class="bc-card">') and "\n" not in html
    assert '<img src="https://cdn.test/duo.jpg" alt="Effaclar Duo+" loading="lazy">' in html
    assert "bc-card-placeholder" not in html
    assert '<div class="bc-card-brand">La Roche-Posay</div>' in html
    assert '<div class="bc-card-name" title="Effaclar Duo+">Effaclar Duo+</div>' in html
    assert '<div class="bc-card-size">40 ml</div>' in html
    assert '<div class="bc-card-price"><span class="bc-from">de la</span> 74,50 lei</div>' in html
    assert '<div class="bc-card-stores">la 2 magazine</div>' in html
    assert '<div class="bc-card-badges"></div>' in html


def test_card_html_single_listing_has_no_de_la() -> None:
    html = card_html(_summary(offer_count=1, retailer_count=1))
    assert '<div class="bc-card-price">74,50 lei</div>' in html
    assert '<div class="bc-card-stores">la 1 magazin</div>' in html


def test_card_html_out_of_stock_and_without_offers() -> None:
    out = card_html(_summary(lowest_price_bani=None, in_stock=False))
    assert '<span class="bc-badge bc-badge-out">Stoc epuizat</span>' in out
    assert '<div class="bc-card-price bc-muted">Indisponibil</div>' in out
    none = card_html(
        _summary(lowest_price_bani=None, in_stock=False, offer_count=0, retailer_count=0)
    )
    assert "bc-badge" not in none  # nothing to be out of stock of
    assert '<div class="bc-card-price bc-muted">Fără oferte încă</div>' in none
    assert '<div class="bc-card-stores">&nbsp;</div>' in none


def test_card_html_keeps_every_line_for_equal_heights() -> None:
    html = card_html(_summary(brand=None, size_value=None))
    assert '<div class="bc-card-brand">&nbsp;</div>' in html
    assert '<div class="bc-card-size">&nbsp;</div>' in html
    assert '<span class="bc-card-placeholder" aria-hidden="true">💄</span>' in html


def test_card_badges() -> None:
    assert card_badges(_summary()) == []
    assert card_badges(_summary(on_sale=True)) == ["Reducere"]
    assert card_badges(_summary(on_sale=True, in_stock=False)) == ["Reducere", "Stoc epuizat"]
    html = card_html(_summary(on_sale=True))
    assert '<span class="bc-badge bc-badge-sale">Reducere</span>' in html


def test_card_html_escapes_scraped_text() -> None:
    html = card_html(
        _summary(
            name='Ser <script>alert(1)</script> "10%"',
            brand="L'Oréal & Co",
            image_url='https://cdn.test/a.jpg" onerror="alert(1)',
        )
    )
    assert "<script>" not in html
    assert "Ser &lt;script&gt;alert(1)&lt;/script&gt; &quot;10%&quot;" in html
    assert "L&#x27;Oréal &amp; Co" in html
    assert 'onerror="' not in html
    assert 'src="https://cdn.test/a.jpg&quot; onerror=&quot;alert(1)"' in html


@pytest.mark.parametrize(
    ("url", "safe"),
    [
        ("https://cdn.test/a.jpg", True),
        ("HTTP://cdn.test/a.jpg", True),
        ("javascript:alert(1)", False),
        ("data:image/png;base64,xx", False),
        ("//cdn.test/a.jpg", False),
        ("", False),
        (None, False),
    ],
)
def test_safe_image_url(url: str | None, safe: bool) -> None:
    assert safe_image_url(url) == (url if safe else None)
    assert ("<img" in card_html(_summary(image_url=url))) is safe


@pytest.mark.parametrize(("total", "pages"), [(0, 1), (1, 1), (24, 1), (25, 2), (48, 2), (49, 3)])
def test_page_count(total: int, pages: int) -> None:
    assert page_count(total, 24) == pages


# --- P7.2 helpers ----------------------------------------------------------------------


def test_discount_pct() -> None:
    assert discount_pct(7_490, 8_990) == 17
    assert discount_pct(8_990, None) is None
    assert discount_pct(8_990, 8_990) is None


NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def _offer(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": 1,
        "retailer": {"slug": "emag", "name": "eMAG"},
        "url": "https://emag.ro/duo",
        "title": "Duo",
        "seller_name": None,
        "price_bani": 7_450,
        "old_price_bani": None,
        "currency": "RON",
        "in_stock": True,
        "last_seen_at": NOW,
        "is_cheapest": False,
    }
    return base | kw


def _detail(*offers: dict[str, object], **kw: object) -> ProductDetail:
    return ProductDetail.model_validate(_summary(**kw).model_dump() | {"offers": list(offers)})


def test_offer_table_html() -> None:
    html = offer_table_html(
        _detail(
            _offer(seller_name="Beauty SRL", old_price_bani=8_990, is_cheapest=True),
            _offer(
                id=2,
                retailer={"slug": "notino", "name": "Notino"},
                url="https://notino.ro/duo",
                price_bani=7_990,
                in_stock=False,
            ),
        )
    )
    assert "\n" not in html
    cheapest, other = re.findall(r"<tr[ >].*?</tr>", html.split("<tbody>")[1])
    assert cheapest.startswith('<tr class="bc-cheapest">')
    assert '<div class="bc-seller">vândut de Beauty SRL</div>' in cheapest
    assert '<div class="bc-best">Cel mai mic preț</div>' in cheapest
    assert '<span class="bc-offer-price">74,50 lei</span>' in cheapest
    assert '<s class="bc-old-price">89,90 lei</s> <span class="bc-discount">-17%</span>' in cheapest
    assert '<span class="bc-stock bc-in-stock">În stoc</span>' in cheapest
    assert (
        '<a class="bc-shop-btn" href="https://emag.ro/duo" target="_blank" '
        'rel="noopener noreferrer nofollow">Vezi în magazin</a>'
    ) in cheapest
    assert other.startswith("<tr>")
    assert "bc-best" not in other and "bc-old-price" not in other
    assert '<span class="bc-stock bc-out-of-stock">Stoc epuizat</span>' in other
    assert 'href="https://notino.ro/duo"' in other


def test_offer_table_html_old_price_without_discount_is_hidden() -> None:
    html = offer_table_html(_detail(_offer(old_price_bani=7_450)))  # "old" = current
    assert "bc-old-price" not in html and "bc-discount" not in html


def test_offer_table_html_escapes_and_drops_unsafe_links() -> None:
    html = offer_table_html(
        _detail(
            _offer(
                retailer={"slug": "x", "name": "<b>Shop</b>"},
                seller_name="A & B",
                url="javascript:alert(1)",
            )
        )
    )
    assert "&lt;b&gt;Shop&lt;/b&gt;" in html and "A &amp; B" in html
    assert "javascript:" not in html and "bc-shop-btn" not in html


def test_product_header_html() -> None:
    above, below = product_header_html(_detail())
    assert above == '<div class="bc-card-brand bc-detail-brand">La Roche-Posay</div>'
    assert '<div class="bc-detail-meta">40 ml</div>' in below
    assert '<span class="bc-from">de la</span> 74,50 lei' in below
    assert '<div class="bc-card-stores">la 2 magazine</div>' in below
    above, below = product_header_html(
        _detail(brand=None, size_value=None, lowest_price_bani=None, offer_count=0)
    )
    assert "&nbsp;" in above
    assert '<div class="bc-detail-meta">&nbsp;</div>' in below
    assert "Fără oferte încă" in below


def test_media_html() -> None:
    assert media_html(_summary(on_sale=True)) == (
        '<div class="bc-card-media"><span class="bc-card-placeholder" aria-hidden="true">'
        '💄</span><div class="bc-card-badges"><span class="bc-badge bc-badge-sale">'
        "Reducere</span></div></div>"
    )


def test_history_rows_extend_to_last_seen_and_gap_when_out_of_stock() -> None:
    history = ProductHistory.model_validate(
        {
            "product_id": 1,
            "series": [
                {
                    "offer_id": 1,
                    "retailer": {"slug": "notino", "name": "Notino"},
                    "seller_name": None,
                    "url": "https://notino.ro/duo",
                    "last_seen_at": NOW,
                    "points": [
                        {
                            "scraped_at": NOW - timedelta(days=9),
                            "price_bani": 8_990,
                            "old_price_bani": None,
                            "in_stock": True,
                        },
                        {
                            "scraped_at": NOW - timedelta(days=3),
                            "price_bani": 8_990,
                            "old_price_bani": None,
                            "in_stock": False,
                        },
                    ],
                },
                {
                    "offer_id": 2,
                    "retailer": {"slug": "emag", "name": "eMAG"},
                    "seller_name": "X",
                    "url": "https://emag.ro/duo",
                    "last_seen_at": NOW - timedelta(days=1),
                    "points": [],
                },
            ],
        }
    )
    assert history_rows(history) == [
        {"Magazin": "Notino", "Data": NOW - timedelta(days=9), "Preț (lei)": 89.9},
        {"Magazin": "Notino", "Data": NOW - timedelta(days=3), "Preț (lei)": None},
        {"Magazin": "Notino", "Data": NOW, "Preț (lei)": None},
    ]


@pytest.mark.parametrize(
    ("lei", "bani"), [(None, None), (0, None), (-5, None), (49.9, 4_990), (0.01, 1), (100, 10_000)]
)
def test_lei_to_bani(lei: float | None, bani: int | None) -> None:
    assert lei_to_bani(lei) == bani


# --- P7.4 helpers ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pct", "in_stock", "label"),
    [
        (-10.0, True, "Sub piață"),
        (-2.0, True, "La nivelul pieței"),
        (0.0, True, "La nivelul pieței"),
        (2.1, True, "Peste piață"),
        (None, True, "—"),
        (-10.0, False, "Stoc epuizat"),
    ],
)
def test_market_position(pct: float | None, in_stock: bool, label: str) -> None:
    assert market_position(pct, in_stock) == label


def test_format_pct() -> None:
    assert (format_pct(11.1), format_pct(-5.0), format_pct(0.0), format_pct(None)) == (
        "+11,1%",
        "-5,0%",
        "+0,0%",
        "—",
    )


def _comparison() -> BrandComparison:
    def price(slug: str, bani: int, vs_median: float | None, in_stock: bool = True) -> object:
        return {
            "retailer": {"slug": slug, "name": slug.title()},
            "price_bani": bani,
            "in_stock": in_stock,
            "vs_min_pct": 0.0,
            "vs_median_pct": vs_median,
            "is_cheapest": False,
        }

    return BrandComparison.model_validate(
        {
            "brand": "La Roche-Posay",
            "retailers": [
                {
                    "retailer": {"slug": "emag", "name": "Emag"},
                    "products_listed": 1,
                    "cheapest_count": 1,
                    "avg_vs_median_pct": -3.5,
                },
                {
                    "retailer": {"slug": "notino", "name": "Notino"},
                    "products_listed": 2,
                    "cheapest_count": 0,
                    "avg_vs_median_pct": None,
                },
            ],
            "total": 2,
            "page": 1,
            "page_size": 100,
            "products": [
                {
                    "product_id": 1,
                    "name": "Effaclar Duo+",
                    "size_value": "40",
                    "size_unit": "ml",
                    "market_min_bani": 7_450,
                    "market_median_bani": 7_720,
                    "prices": [price("emag", 7_450, -3.5), price("notino", 7_990, 3.5)],
                },
                {
                    "product_id": 2,
                    "name": "Cicaplast",
                    "size_value": None,
                    "size_unit": None,
                    "market_min_bani": None,
                    "market_median_bani": None,
                    "prices": [price("notino", 5_500, None, in_stock=False)],
                },
            ],
        }
    )


def test_position_cards_html() -> None:
    html = position_cards_html(_comparison())
    assert "\n" not in html and html.startswith('<div class="bc-stats">')
    emag, notino = html.split('<div class="bc-stat">')[1:]
    assert '<div class="bc-stat-store">Emag</div>' in emag
    assert '<span class="bc-pill bc-below">-3,5%</span>' in emag
    assert "cel mai ieftin la 1 din 1 produs" in emag
    assert '<span class="bc-pill">—</span>' in notino  # no in-stock price: neutral
    assert "cel mai ieftin la 0 din 2 produse" in notino


@pytest.mark.parametrize(
    ("value", "style"),
    [
        (None, ""),
        ("—", ""),
        (float("nan"), ""),
        (0.0, ""),
        (2.0, ""),  # inside the ±2 % band
        (-2.0, ""),
        (-4.0, "background-color: rgba(46, 160, 67, 0.19)"),
        (10.0, "background-color: rgba(218, 54, 51, 0.29)"),
        (20.0, "background-color: rgba(218, 54, 51, 0.45)"),
        (-80.0, "background-color: rgba(46, 160, 67, 0.45)"),  # capped
    ],
)
def test_pct_cell_style(value: object, style: str) -> None:
    assert pct_cell_style(value) == style


def test_position_style_and_legend() -> None:
    assert position_style("Sub piață") == "background-color: rgba(46, 160, 67, 0.20)"
    assert position_style("Peste piață") == "background-color: rgba(218, 54, 51, 0.20)"
    assert position_style("La nivelul pieței") == position_style("Stoc epuizat") == ""
    assert "(±2%)" in MARKET_LEGEND_HTML
    assert MARKET_LEGEND_HTML.count("bc-pill") == 3


def test_retailer_rows_skip_unlisted_products() -> None:
    comparison = _comparison()
    assert [r["Produs"] for r in retailer_rows(comparison, "emag")] == ["Effaclar Duo+"]
    notino = retailer_rows(comparison, "notino")
    assert notino[0] == {
        "Produs": "Effaclar Duo+",
        "Mărime": "40 ml",
        "Prețul magazinului": "79,90 lei",
        "Minim piață": "74,50 lei",
        "Median piață": "77,20 lei",
        "Față de median": "+3,5%",
        "Poziție": "Peste piață",
    }
    assert notino[1]["Poziție"] == "Stoc epuizat"
    assert retailer_rows(comparison, "sephora") == []


def test_matrix_rows() -> None:
    assert matrix_rows(_comparison()) == [
        {"Produs": "Effaclar Duo+", "Emag": -3.5, "Notino": 3.5},
        {"Produs": "Cicaplast", "Emag": None, "Notino": None},
    ]
