from decimal import Decimal

import pytest

from beautycrawler.normalization.size import Size, parse_size


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("La Roche-Posay Effaclar Duo+ 40 ml", Size(Decimal(40), "ml")),
        ("Bioderma Sensibio H2O 500ML", Size(Decimal(500), "ml")),
        ("Niacinamide 10% + Zinc 1% 30ml", Size(Decimal(30), "ml")),
        ("Crema 50ml SPF 50", Size(Decimal(50), "ml")),
        ("Șampon 400 ML", Size(Decimal(400), "ml")),
        ("Parfum 100 ml / 3.4 oz", Size(Decimal(100), "ml")),
        ("Lotiune 200 ml 200 ml", Size(Decimal(200), "ml")),  # repeated, same size
        # litres/kg converted to ml/g
        ("Apa micelara 1,5 l", Size(Decimal(1500), "ml")),
        ("EDT 0.5 L", Size(Decimal(500), "ml")),
        ("Gel de duș 1 litru", Size(Decimal(1000), "ml")),
        ("Parfum 7,5 cl", Size(Decimal(75), "ml")),
        ("Balsam 1 kg", Size(Decimal(1000), "g")),
        ("Pudră 9 g", Size(Decimal(9), "g")),
        ("Pudră compactă 9gr", Size(Decimal(9), "g")),
        ("Unt de corp 200 grame", Size(Decimal(200), "g")),
        ("Pudra 2,5 g", Size(Decimal("2.5"), "g")),
        # pieces
        ("Discuri demachiante 80 buc", Size(Decimal(80), "buc")),
        ("Vitamina C 60 capsule", Size(Decimal(60), "buc")),
        ("Plasturi anti-acnee 24 plasturi", Size(Decimal(24), "buc")),
        ("Fiole par 10 fiole", Size(Decimal(10), "buc")),
        ("Masca 5 bucăți", Size(Decimal(5), "buc")),
        # multipacks
        ("Set 2 x 50 ml", Size(Decimal(50), "ml", 2)),
        ("2x50ml duo", Size(Decimal(50), "ml", 2)),
        ("Gel de dus 250 ml x 3", Size(Decimal(250), "ml", 3)),
        ("Masca 2 buc x 25 ml", Size(Decimal(25), "ml", 2)),
        ("Set 2 x 50 ml (100 ml)", Size(Decimal(50), "ml", 2)),  # total repeated
        ("Pachet 3 X 1,5 l", Size(Decimal(1500), "ml", 3)),
    ],
)
def test_parse_size(title: str, expected: Size) -> None:
    assert parse_size(title) == expected


@pytest.mark.parametrize(
    "title",
    [
        None,
        "",
        "Cremă hidratantă",  # no size
        "Crema 30 lei",  # price, not a size
        "Gel 5 gel",  # 'g' followed by letters
        "Crema SPF 50",
        "Ser vitamina C 15%",
        "Set: cremă 50 ml + ser 30 ml",  # gift set with two sizes
        "Rimel 12 ml x 2 + demachiant 50 ml",
        "Ser 30 ml (2 buc)",  # ambiguous: 30 ml total or 2 x 30 ml?
        "Crema 0 ml",
    ],
)
def test_parse_size_none(title: str | None) -> None:
    assert parse_size(title) is None


def test_total_and_str() -> None:
    assert Size(Decimal(50), "ml", 2).total == Decimal(100)
    assert str(Size(Decimal(50), "ml", 2)) == "2 x 50 ml"
    assert str(Size(Decimal("2.5"), "g")) == "2.5 g"
    assert str(parse_size("Apa 1,5 l")) == "1500 ml"


def test_equal_sizes_in_different_units_are_equal() -> None:
    assert parse_size("1,5 l") == parse_size("1500 ml")
    assert parse_size("1 kg") == parse_size("1000 g")
