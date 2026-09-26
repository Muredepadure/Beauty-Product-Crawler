from decimal import Decimal

import pytest

from beautycrawler.api.schemas import ProductSummary
from beautycrawler.ui_data import (
    card_price_line,
    card_subtitle,
    format_size,
    page_count,
    plural_ro,
    products_label,
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
