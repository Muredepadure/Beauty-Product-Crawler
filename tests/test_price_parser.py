from decimal import Decimal

import pytest

from beautycrawler.extractors.price import (
    extract_prices,
    parse_machine_price,
    parse_price,
    parse_price_pair,
)

NBSP = chr(0x00A0)
NNBSP = chr(0x202F)


@pytest.mark.parametrize(
    ("text", "bani"),
    [
        # Romanian format: dot thousands, comma decimals
        ("1.234,99 lei", 123499),
        ("1.234.567,89 lei", 123456789),
        ("49,90 RON", 4990),
        ("49,9 lei", 4990),
        ("0,99 lei", 99),
        ("49,90 Lei", 4990),
        ("49,90 LEI", 4990),
        ("1 leu", 100),
        # dot decimals (several shops use them)
        ("129.99 lei", 12999),
        ("129.9 lei", 12990),
        # English-style thousands
        ("1,234.99 lei", 123499),
        # thousands only
        ("1.234 lei", 123400),
        ("1,234 lei", 123400),
        ("12 345,50 lei", 1234550),
        (f"1{NBSP}299,00{NBSP}lei", 129900),
        (f"1{NNBSP}299 lei", 129900),
        # integers
        ("30 lei", 3000),
        ("99 RON", 9900),
        # currency first
        ("Lei 1 299", 129900),
        ("RON 49.90", 4990),
        ("lei 49,90", 4990),
        # surrounding text
        ("de la 30 lei", 3000),
        ("De la 1.299,00 lei", 129900),
        ("Preț: 89,99 lei", 8999),
        ("Pret redus 89,99lei", 8999),
        ("-20% 79,99 lei", 7999),
        ("Reducere -15 % acum 42,50 lei", 4250),
        ("Effaclar Duo+ 40 ml 89,99 lei", 8999),  # size is not the price
        # no currency: first number
        ("79,99", 7999),
        ("  1.299,00  ", 129900),
    ],
)
def test_parse_price(text: str, bani: int) -> None:
    assert parse_price(text) == bani


@pytest.mark.parametrize("text", [None, "", "   ", "Stoc epuizat", "Preț la cerere", "lei"])
def test_parse_price_none(text: str | None) -> None:
    assert parse_price(text) is None


def test_extract_prices_only_currency_marked_numbers() -> None:
    text = "Set 2 x 50 ml, -30%: 129,99 lei 90,99 lei, livrare gratuită peste 150 lei"
    assert extract_prices(text) == [12999, 9099, 15000]


def test_extract_prices_empty() -> None:
    assert extract_prices(None) == []
    assert extract_prices("40 ml, 3 buc, -10%") == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Preț vechi: 129,99 lei Preț nou: 99,99 lei (-23%)", (9999, 12999)),
        ("99,99 lei 129,99 lei", (9999, 12999)),  # order on the page doesn't matter
        ("PRP: 1.299,00 lei | 999,00 lei", (99900, 129900)),
        ("89,99 lei", (8999, None)),
        ("89,99 lei 89,99 lei", (8999, None)),  # same amount twice: not a sale
        ("no price here", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_price_pair(text: str | None, expected: tuple[int | None, int | None]) -> None:
    assert parse_price_pair(text) == expected


@pytest.mark.parametrize(
    ("value", "bani"),
    [
        ("49.90", 4990),
        ("49,90", 4990),  # comma decimal in structured data
        ("49.9", 4990),
        ("1234.5", 123450),
        ("1234,50", 123450),
        ("1.234", 123),  # machine format: lone dot is decimal (1.234 lei -> 123 bani)
        ("1,234.50", 123450),
        ("1.234,50", 123450),
        (" 49.90 RON ", 4990),
        ("49.90 lei", 4990),
        (f"1{NBSP}234,50", 123450),
        (49.9, 4990),
        (30, 3000),
        (Decimal("19.995"), 2000),  # half-up rounding
        (0, 0),
    ],
)
def test_parse_machine_price(value: object, bani: int) -> None:
    assert parse_machine_price(value) == bani


@pytest.mark.parametrize(
    "value", [None, "", "abc", "-1", -5, True, "NaN", "Infinity", float("nan"), [49.9], {}]
)
def test_parse_machine_price_invalid(value: object) -> None:
    assert parse_machine_price(value) is None
