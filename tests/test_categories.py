"""P13.3: product categories from product names."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from beautycrawler.db import Base
from beautycrawler.db.models import Brand, Offer, Product, Retailer
from beautycrawler.db.session import make_engine, make_session_factory
from beautycrawler.matching.__main__ import main as matching_main
from beautycrawler.normalization.categories import (
    CATEGORIES,
    OTHER,
    categorize,
    categorize_products,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # XpertBeauty: the type comes first
        (
            "Vopsea de par L'Oreal Professionnel Majirel 6.3 Blond Inchis Auriu 50ml",
            "Vopsea & oxidant",
        ),
        ("Oxidant Wella Professionals Welloxon Perfect 6%, 1000ml", "Vopsea & oxidant"),
        ("Sampon L'Oréal Professionnel Serie Expert Vitamino Color 500ml", "Șampon"),
        ("Balsam de par Kerastase Reflection Fondant Chromatique 200ml", "Balsam"),
        ("Masca de par Moroccanoil Repair 500ml", "Mască de păr"),
        (
            "Ulei de par bifazic L’Oreal Professionnel Absolut Repair 90ml",
            "Tratament & îngrijire păr",
        ),
        ("Fixativ de par Wella Professionals Eimi Glam Mist 200ml", "Styling"),
        ("Lac unghii semipermanent Gelish Soak-Off Gel Passion 15 ml", "Unghii"),
        ("Pudra acrilica sistem Gelish Dip Luxe Be a Lady 23 gr", "Unghii"),
        ("Mascara rezistent la apa Kryolan Waterproof Black 6ml", "Machiaj"),
        ("Set Kerastase Nutritive Duo pentru par foarte uscat, 250ml+200ml", "Seturi & cadouri"),
        ("Uscator de par Parlux 385 Powerlight Purple", "Accesorii & aparate"),
        ("Lotiune tonica Mary Cohr pentru tenul gras 200ml", "Îngrijire față"),
        ("Ceara Depileve Traditionala Pink 1Kg", "Îngrijire corp"),
        # Profihairshop: brand first, upper case
        ("ORLY Lac de unghii GOTTA BOUNCE 18 ML", "Unghii"),
        ("KAYPRO ANTIYELLOW GIGS Sampon cu efect anti-ingalbenire 350 ML", "Șampon"),
        ("NATURAL KAY Oxidant 12% (40 vol) 1000 ML", "Vopsea & oxidant"),
        ("COMAIR, Perie paddle 13 randuri cu peri de mistret", "Accesorii & aparate"),
        ("T-LAB Root Power spray pentru re-cresterea parului 150 ML", "Tratament & îngrijire păr"),
        ("IDC Institute Scented Bath Gold Set cadou baie cutie 6 piese", "Seturi & cadouri"),
        # Parfimo: brand first, mixed Romanian/English
        ("Gucci Bloom Apă de parfum pentru femei 50 ml", "Parfumuri"),
        ("Dunhill Desire Blue Apă de toaletă pentru bărbați 100 ml", "Parfumuri"),
        ("Trussardi Trussardi EDP 30 ml W", "Parfumuri"),
        ("Kallos Multivitamin Energising Shampoo 1000 ml", "Șampon"),
        ("Hugo Boss Boss The Scent For Him Gel de duș pentru bărbați 150 ml", "Îngrijire corp"),
        ("Revolution Man Set cadou Apă de toaletă 100 ml + gel de duș 150 ml", "Seturi & cadouri"),
        ("Artdeco High Performance Eyeshadow Stylo 1,4 g", "Machiaj"),
        ("Mario Badescu Caffeine Eye Cream 14 g", "Îngrijire față"),
        ("Medik8 HYDR8 B5 Liquid Rehydration Serum 30 ml", "Îngrijire față"),
        ("By Eloise London Metallic Gold Quatrefoil", OTHER),
    ],
)
def test_categorize_real_names(name: str, expected: str) -> None:
    assert categorize(name) == expected
    assert expected in CATEGORIES


def test_categorize_ignores_case_and_diacritics() -> None:
    assert categorize("ȘAMPON REPARATOR") == categorize("sampon reparator") == "Șampon"


def _setup(session: Session) -> dict[str, Product]:
    shop = Retailer(slug="shop", name="Shop", domain="shop.ro")
    brand = Brand(name="Wella", normalized_name="wella")
    named = Product(brand=brand, name="Invigo Sampon Color 300 ml", normalized_name="a")
    vague = Product(brand=brand, name="Invigo Color Brilliance", normalized_name="b")
    known = Product(brand=brand, name="Fixativ X", normalized_name="c", category="Curățare")
    session.add_all([shop, named, vague, known])
    # The vague name says nothing; its listing's title does.
    session.add(
        Offer(
            retailer=shop,
            product=vague,
            url="https://shop.ro/1",
            title="Masca de par Wella Invigo Color Brilliance 150ml",
            price_bani=1_000,
            in_stock=True,
        )
    )
    session.commit()
    return {"named": named, "vague": vague, "known": known}


def test_categorize_products_fills_only_missing(session: Session) -> None:
    products = _setup(session)
    counts = categorize_products(session)
    assert counts == {"Șampon": 1, "Mască de păr": 1}
    assert products["named"].category == "Șampon"
    assert products["vague"].category == "Mască de păr"  # from the listing's title
    assert products["known"].category == "Curățare"  # left alone
    assert categorize_products(session, recompute=True)["Styling"] == 1
    assert products["known"].category == "Styling"


def test_categorize_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    url = f"sqlite:///{tmp_path / 'c.db'}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        _setup(session)
    engine.dispose()
    assert matching_main(["--database-url", url, "categorize"]) == 0
    out = capsys.readouterr().out
    assert "Șampon" in out and "Mască de păr" in out
    assert matching_main(["--database-url", url, "categorize"]) == 0
    assert "Every product already has a category." in capsys.readouterr().out
