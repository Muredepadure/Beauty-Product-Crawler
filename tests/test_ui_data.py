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
    card_price_line,
    card_subtitle,
    discount_pct,
    format_pct,
    format_size,
    history_rows,
    lei_to_bani,
    market_position,
    matrix_rows,
    offer_rows,
    page_count,
    plural_ro,
    position_rows,
    products_label,
    retailer_rows,
    stores_label,
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


def test_card_lines() -> None:
    assert card_price_line(_summary()) == "de la 74,50 lei · 2 magazine"
    assert card_price_line(_summary(lowest_price_bani=None, in_stock=False)) == (
        "Stoc epuizat · 2 magazine"
    )
    assert card_price_line(_summary(lowest_price_bani=None, offer_count=0, retailer_count=0)) == (
        "Fără oferte încă"
    )
    assert card_subtitle(_summary()) == "La Roche-Posay · 40 ml"
    assert card_subtitle(_summary(brand=None, size_value=None)) == ""


@pytest.mark.parametrize(("total", "pages"), [(0, 1), (1, 1), (24, 1), (25, 2), (48, 2), (49, 3)])
def test_page_count(total: int, pages: int) -> None:
    assert page_count(total, 24) == pages


# --- P7.2 helpers ----------------------------------------------------------------------


def test_discount_pct() -> None:
    assert discount_pct(7_490, 8_990) == 17
    assert discount_pct(8_990, None) is None
    assert discount_pct(8_990, 8_990) is None


NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def test_offer_rows() -> None:
    detail = ProductDetail.model_validate(
        _summary().model_dump()
        | {
            "offers": [
                {
                    "id": 1,
                    "retailer": {"slug": "emag", "name": "eMAG"},
                    "url": "https://emag.ro/duo",
                    "title": "Duo",
                    "seller_name": "Beauty SRL",
                    "price_bani": 7_450,
                    "old_price_bani": 8_990,
                    "currency": "RON",
                    "in_stock": True,
                    "last_seen_at": NOW,
                    "is_cheapest": True,
                }
            ]
        }
    )
    assert offer_rows(detail) == [
        {
            "": "🏆",
            "Magazin": "eMAG (vândut de Beauty SRL)",
            "Preț": "74,50 lei",
            "Preț vechi": "89,90 lei",
            "Reducere": "-17%",
            "Stoc": "În stoc",
            "Link": "https://emag.ro/duo",
        }
    ]


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


def test_position_rows() -> None:
    assert position_rows(_comparison()) == [
        {
            "Magazin": "Emag",
            "Produse listate": 1,
            "Cel mai ieftin la": 1,
            "Medie față de median": "-3,5%",
        },
        {
            "Magazin": "Notino",
            "Produse listate": 2,
            "Cel mai ieftin la": 0,
            "Medie față de median": "—",
        },
    ]


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
