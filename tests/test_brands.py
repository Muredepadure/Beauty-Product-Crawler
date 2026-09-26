import pytest

from beautycrawler.normalization import brands
from beautycrawler.normalization.brands import (
    BRANDS,
    brand_key,
    canonical_brand,
    is_known_brand,
)


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("La Roche-Posay", "la roche posay"),
        ("LA ROCHE POSAY", "la roche posay"),
        ("la roche-posay®", "la roche posay"),
        ("L'Oréal Paris", "loreal paris"),
        ("L’OREAL PARIS", "loreal paris"),
        ("Kiehl's Since 1851", "kiehls since 1851"),
        ("  Estée   Lauder™ ", "estee lauder"),
        ("A-Derma", "a derma"),
        ("The Ordinary.", "the ordinary"),
        ("Farmec Și Gerovital", "farmec si gerovital"),
    ],
)
def test_brand_key(raw: str, key: str) -> None:
    assert brand_key(raw) == key


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("L'Oreal Paris", "L'Oréal Paris"),
        ("L’Oréal", "L'Oréal Paris"),
        ("LOREAL PARIS", "L'Oréal Paris"),
        ("L'Oreal Professionnel", "L'Oréal Professionnel"),  # separate brand
        ("la roche posay", "La Roche-Posay"),
        ("LA ROCHE-POSAY®", "La Roche-Posay"),
        ("Eau Thermale Avène", "Avène"),
        ("AVENE", "Avène"),
        ("YSL", "Yves Saint Laurent"),
        ("Maybelline", "Maybelline New York"),
        ("NYX", "NYX Professional Makeup"),
        ("CERAVE", "CeraVe"),
        ("Kiehls", "Kiehl's"),
        ("Aderma", "A-Derma"),
    ],
)
def test_canonical_brand_known(raw: str, canonical: str) -> None:
    assert canonical_brand(raw) == canonical
    assert is_known_brand(raw)


def test_canonical_brand_unknown_is_cleaned_not_invented() -> None:
    assert canonical_brand("  Beauty   of Joseon™ ") == "Beauty of Joseon"
    assert not is_known_brand("Beauty of Joseon")


@pytest.mark.parametrize("raw", [None, "", "   ", "®"])
def test_canonical_brand_empty(raw: str | None) -> None:
    assert canonical_brand(raw) is None


def test_every_canonical_name_maps_to_itself() -> None:
    for name in BRANDS:
        assert canonical_brand(name) == name


def test_conflicting_alias_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(brands, "BRANDS", {"Dior": ("CD",), "Chanel": ("cd",)})
    brands._alias_index.cache_clear()
    try:
        with pytest.raises(ValueError, match="maps to"):
            canonical_brand("x")
    finally:
        monkeypatch.undo()
        brands._alias_index.cache_clear()
