"""P4.4 product matching: name keys, scoring guards and the DB matching service.

Titles below are written the way Romanian retailers typically phrase them (brand
first or buried mid-title, Romanian descriptors, promo noise, "40ml" vs "40 ml").
"""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from beautycrawler.db.models import Brand, MatchCandidate, Offer, Product, Retailer
from beautycrawler.matching.keys import (
    base_size,
    display_name,
    name_tokens,
    offer_size,
    score_pair,
)
from beautycrawler.matching.service import (
    MatchConfig,
    MatchMethod,
    match_offer,
    match_unmatched,
)
from beautycrawler.normalization.size import strip_sizes

# EAN-13s with valid check digits (not real products).
EAN_A = "5901234123457"
EAN_B = "4006381333931"


# --- name keys ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "brand", "expected"),
    [
        ("La Roche-Posay Effaclar Duo+ 40 ml", "La Roche-Posay", ("effaclar", "duo", "plus")),
        ("LA ROCHE POSAY Effaclar DUO(+) 40ml", "LRP", ("effaclar", "duo", "plus")),
        # brand in the middle, Romanian filler words, promo noise
        (
            "Cremă corectoare La Roche-Posay Effaclar Duo+ pentru ten gras -20%",
            "La Roche-Posay",
            ("crema", "corectoare", "effaclar", "duo", "plus", "ten", "gras"),
        ),
        # apostrophe brands and aliases
        ("L’Oréal Paris Revitalift Filler 30 ml", "L'Oreal", ("revitalift", "filler")),
        # a "+" between words is a separator, not a "plus" variant
        (
            "Maybelline Fit Me Matte+Poreless 110",
            "Maybelline New York",
            ("fit", "me", "matte", "poreless", "110"),
        ),
        (
            "The Ordinary Niacinamide 10% + Zinc 1%",
            None,
            ("ordinary", "niacinamide", "10", "zinc", "1"),  # "the" is a filler word
        ),
    ],
)
def test_name_tokens(title: str, brand: str | None, expected: tuple[str, ...]) -> None:
    assert name_tokens(title, brand) == expected


def test_display_name_strips_leading_brand_size_and_noise() -> None:
    assert (
        display_name("PROMO La Roche-Posay Effaclar Duo+ cremă 40 ml", "La Roche-Posay")
        == "Effaclar Duo+ cremă"
    )
    # brand not at the start: kept as written
    assert display_name("Cremă CeraVe hidratantă 50 ml", "CeraVe") == "Cremă CeraVe hidratantă"
    # nothing but brand and size left: fall back to the cleaned title
    assert display_name("Nivea 50 ml", "Nivea") == "Nivea 50 ml"


def test_strip_sizes() -> None:
    assert strip_sizes("Ser 2 x 30 ML nou") == "Ser nou"
    assert strip_sizes("Vitamina C 60 capsule") == "Vitamina C"
    assert strip_sizes("Gel 5 gel") == "Gel 5 gel"  # "5 gel" is not a size


# --- scoring guards ----------------------------------------------------------------


def _score(a: str, b: str, brand: str) -> tuple[float, str | None, tuple[str, ...]]:
    pair = score_pair(name_tokens(a, brand), name_tokens(b, brand))
    return pair.score, pair.conflict, pair.doubts


def test_same_product_different_wording_scores_high() -> None:
    score, conflict, doubts = _score(
        "L'Oréal Paris Revitalift Filler ser cu acid hialuronic 30 ml",
        "Ser L'Oreal Paris Revitalift Filler acid hialuronic 30ml PROMO",
        "L'Oréal Paris",
    )
    assert score >= 90 and conflict is None and doubts == ()


def test_variant_letter_is_a_doubt_not_a_match() -> None:
    score, conflict, doubts = _score(
        "La Roche-Posay Effaclar Duo+", "La Roche-Posay Effaclar Duo+M", "La Roche-Posay"
    )
    assert conflict is None
    assert doubts  # "m" only on one side
    assert score >= 75


def test_plus_variant_is_a_doubt() -> None:
    _, _, doubts = _score("Cicaplast Baume B5", "Cicaplast Baume B5+", "La Roche-Posay")
    assert doubts and "plus" in doubts[0]


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Anthelios UVMune 400 SPF 50+ fluid", "Anthelios UVMune 400 SPF 30 fluid"),
        ("Fit Me Matte+Poreless 110 Porcelain", "Fit Me Matte+Poreless 120 Classic Ivory"),
        ("Niacinamide 10% + Zinc 1%", "Niacinamide 5% + Zinc 1%"),
    ],
)
def test_different_numbers_conflict(a: str, b: str) -> None:
    assert score_pair(name_tokens(a), name_tokens(b)).conflict is not None


def test_empty_key_conflicts() -> None:
    assert score_pair((), ("x",)).conflict == "empty name"


# --- sizes -------------------------------------------------------------------------


def test_base_size_units() -> None:
    assert base_size(Decimal("1"), "l") == (Decimal(1000), "ml")
    assert base_size(Decimal("0.5"), "kg") == (Decimal(500), "g")
    assert base_size(Decimal("40.000"), "ml") == (Decimal(40), "ml")
    assert base_size(None, "ml") is None
    assert base_size(Decimal(1), "oz") is None


def test_offer_size_prefers_fields_and_detects_packs() -> None:
    assert offer_size("Crema 50 ml", Decimal(40), "ml") == ((Decimal(40), "ml"), 1)
    assert offer_size("Crema 50 ml", None, None) == ((Decimal(50), "ml"), 1)
    assert offer_size("Set 2 x 50 ml", None, None) == ((Decimal(50), "ml"), 2)
    # size field holds the pack total
    assert offer_size("Set 2 x 50 ml", Decimal(100), "ml") == ((Decimal(50), "ml"), 2)
    assert offer_size("Crema", None, None) == (None, 1)


# --- matching service --------------------------------------------------------------


@pytest.fixture
def retailers(session: Session) -> dict[str, Retailer]:
    rows = {
        slug: Retailer(slug=slug, name=slug.title(), domain=f"{slug}.ro")
        for slug in ("notino", "emag", "sephora", "drmax")
    }
    session.add_all(rows.values())
    session.flush()
    return rows


def _brand(session: Session, name: str, key: str) -> Brand:
    brand = session.scalars(select(Brand).where(Brand.normalized_name == key)).one_or_none()
    if brand is None:
        brand = Brand(name=name, normalized_name=key)
        session.add(brand)
    return brand


def _product(
    session: Session,
    name: str,
    *,
    brand: tuple[str, str] = ("La Roche-Posay", "la roche posay"),
    size: str | None = "40",
    unit: str | None = "ml",
    ean: str | None = None,
) -> Product:
    product = Product(
        brand=_brand(session, *brand),
        name=name,
        normalized_name=name.lower(),
        size_value=Decimal(size) if size else None,
        size_unit=unit,
        ean=ean,
    )
    session.add(product)
    session.flush()
    return product


_url_counter = iter(range(10_000))


def _offer(
    session: Session,
    retailer: Retailer,
    title: str,
    *,
    brand: str | None = "La Roche-Posay",
    size: str | None = None,
    unit: str | None = None,
    ean: str | None = None,
) -> Offer:
    offer = Offer(
        retailer=retailer,
        url=f"https://{retailer.domain}/p/{next(_url_counter)}",
        title=title,
        brand_name=brand,
        ean=ean,
        size_value=Decimal(size) if size else None,
        size_unit=unit,
        price_bani=9_990,
        in_stock=True,
    )
    session.add(offer)
    session.flush()
    return offer


def _pending(session: Session, offer: Offer) -> list[MatchCandidate]:
    return list(
        session.scalars(
            select(MatchCandidate).where(
                MatchCandidate.offer_id == offer.id, MatchCandidate.status == "pending"
            )
        )
    )


def test_ean_exact_match_wins_over_names(session: Session, retailers: dict[str, Retailer]) -> None:
    product = _product(session, "Effaclar Duo+", ean=EAN_A)
    # Title is unhelpful, but the GTIN is the same.
    offer = _offer(session, retailers["emag"], "Crema anti-imperfectiuni 40ml", ean=EAN_A)
    result = match_offer(session, offer)
    assert result.method is MatchMethod.EAN
    assert offer.product is product


def test_fuzzy_auto_match_across_retailers(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    product = _product(
        session,
        "Revitalift Filler ser cu acid hialuronic",
        brand=("L'Oréal Paris", "loreal paris"),
        size="30",
    )
    offer = _offer(
        session,
        retailers["emag"],
        "Ser L’Oreal Paris Revitalift Filler acid hialuronic, 30ml PROMO",
        brand="L'Oreal",
        ean=EAN_B,
    )
    result = match_offer(session, offer)
    assert result.method is MatchMethod.FUZZY
    assert offer.product is product
    assert product.ean == EAN_B  # learned from the offer, so the next match is exact
    assert _pending(session, offer) == []


def test_size_mismatch_is_never_a_candidate(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    _product(session, "Effaclar Duo+", size="40")
    offer = _offer(session, retailers["notino"], "La Roche-Posay Effaclar Duo+ 15 ml")
    result = match_offer(session, offer)
    assert result.method is MatchMethod.NEW_PRODUCT
    assert result.product is not None
    assert (result.product.size_value, result.product.size_unit) == (Decimal(15), "ml")
    assert result.product.name == "Effaclar Duo+"


def test_litres_and_millilitres_compare_equal(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    product = _product(
        session, "Sensibio H2O apa micelara", brand=("Bioderma", "bioderma"), size="1", unit="l"
    )
    offer = _offer(
        session,
        retailers["drmax"],
        "Bioderma Sensibio H2O apă micelară 1000 ml",
        brand="BIODERMA",
    )
    assert match_offer(session, offer).product is product


def test_different_ean_is_never_a_candidate(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    _product(session, "Effaclar Duo+", ean=EAN_A)
    offer = _offer(session, retailers["notino"], "La Roche-Posay Effaclar Duo+ 40 ml", ean=EAN_B)
    result = match_offer(session, offer)
    assert result.method is MatchMethod.NEW_PRODUCT
    assert result.product is not None and result.product.ean == EAN_B


def test_variant_goes_to_review_not_auto_merge(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    duo = _product(session, "Effaclar Duo+")
    offer = _offer(session, retailers["sephora"], "La Roche-Posay Effaclar Duo+M 40ml")
    result = match_offer(session, offer)
    assert result.method is MatchMethod.REVIEW
    assert offer.product is None
    [row] = _pending(session, offer)
    assert row.product_id == duo.id
    assert "variant markers" in row.reason


def test_verbose_titles_of_the_same_product_go_to_review(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    """Two retailers describing one product in very different words: plausible, but
    not certain enough to merge without a human."""
    first = _offer(
        session,
        retailers["notino"],
        "La Roche-Posay Effaclar DUO(+) cremă corectoare anti-imperfecțiuni 40 ml",
    )
    assert match_offer(session, first).method is MatchMethod.NEW_PRODUCT
    second = _offer(
        session,
        retailers["emag"],
        "Cremă corectoare La Roche-Posay Effaclar Duo+ pentru ten gras cu tendință acneică, 40 ml",
    )
    result = match_offer(session, second)
    assert result.method is MatchMethod.REVIEW
    assert [c.product for c in result.candidates] == [first.product]


def test_unknown_size_goes_to_review(session: Session, retailers: dict[str, Retailer]) -> None:
    _product(session, "Effaclar Duo+", size=None, unit=None)
    offer = _offer(session, retailers["notino"], "La Roche-Posay Effaclar Duo+ 40 ml")
    result = match_offer(session, offer)
    assert result.method is MatchMethod.REVIEW
    assert "size unknown" in _pending(session, offer)[0].reason


def test_close_runner_up_goes_to_review(session: Session, retailers: dict[str, Retailer]) -> None:
    a = _product(session, "Hydrating Cleanser", brand=("CeraVe", "cerave"), size="236")
    b = _product(session, "Hydrating Cleanser gel", brand=("CeraVe", "cerave"), size="236")
    offer = _offer(session, retailers["emag"], "CeraVe Hydrating Cleanser 236 ml", brand="CeraVe")
    result = match_offer(session, offer)
    assert result.method is MatchMethod.REVIEW
    assert {r.product_id for r in _pending(session, offer)} == {a.id, b.id}
    assert all("several close matches" in r.reason for r in _pending(session, offer))


def test_different_products_of_same_brand_stay_apart(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    _product(session, "Anthelios UVMune 400 SPF 50+ fluid invizibil", size="50")
    offer = _offer(
        session, retailers["notino"], "La Roche-Posay Anthelios UVMune 400 SPF 30 fluid 50 ml"
    )
    assert match_offer(session, offer).method is MatchMethod.NEW_PRODUCT


def test_other_brands_are_not_considered(session: Session, retailers: dict[str, Retailer]) -> None:
    _product(session, "Hydrating Cleanser", brand=("CeraVe", "cerave"), size="236")
    offer = _offer(session, retailers["emag"], "Hydrating Cleanser 236 ml", brand="Generic Brand")
    result = match_offer(session, offer)
    assert result.method is MatchMethod.NEW_PRODUCT
    assert result.product is not None and result.product.brand is not None
    assert result.product.brand.name == "Generic Brand"


def test_offer_without_brand_is_left_unmatched(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    offer = _offer(session, retailers["emag"], "Crema de fata 50 ml", brand=None)
    result = match_offer(session, offer)
    assert (result.method, result.note) == (MatchMethod.UNMATCHED, "brand unknown")
    assert session.scalars(select(Product)).all() == []


def test_multipack_is_not_turned_into_a_single_product(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    offer = _offer(session, retailers["emag"], "La Roche-Posay Effaclar Duo+ 2 x 40 ml")
    result = match_offer(session, offer)
    assert (result.method, result.note) == (MatchMethod.UNMATCHED, "multipack of 2")


def test_multipack_of_known_product_goes_to_review(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    _product(session, "Effaclar Duo+")
    offer = _offer(session, retailers["emag"], "La Roche-Posay Effaclar Duo+ 2 x 40 ml")
    assert match_offer(session, offer).method is MatchMethod.REVIEW
    assert "multipack of 2" in _pending(session, offer)[0].reason


def test_new_product_reuses_canonical_brand(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    lrp = _brand(session, "La Roche-Posay", "la roche posay")
    offer = _offer(
        session, retailers["notino"], "LRP Cicaplast Baume B5+ 40 ml", brand="LA ROCHE POSAY"
    )
    result = match_offer(session, offer)
    assert result.product is not None and result.product.brand is lrp
    assert session.scalars(select(Brand)).all() == [lrp]


def test_create_products_can_be_disabled(session: Session, retailers: dict[str, Retailer]) -> None:
    offer = _offer(session, retailers["notino"], "La Roche-Posay Effaclar Duo+ 40 ml")
    result = match_offer(session, offer, MatchConfig(create_products=False))
    assert result.method is MatchMethod.UNMATCHED
    assert offer.product is None


def test_already_linked_offer_is_untouched(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    product = _product(session, "Effaclar Duo+")
    offer = _offer(session, retailers["notino"], "Something else entirely")
    offer.product = product
    assert match_offer(session, offer).method is MatchMethod.ALREADY_LINKED


def test_rejected_candidate_is_not_proposed_again(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    _product(session, "Effaclar Duo+")
    offer = _offer(session, retailers["sephora"], "La Roche-Posay Effaclar Duo+M 40ml")
    match_offer(session, offer)
    [row] = _pending(session, offer)
    row.status = "rejected"
    session.flush()

    result = match_offer(session, offer)
    assert result.method is MatchMethod.NEW_PRODUCT  # the only candidate was rejected
    assert result.product is not None and result.product.name == "Effaclar Duo+M"


def test_pending_review_is_not_rematched(session: Session, retailers: dict[str, Retailer]) -> None:
    _product(session, "Effaclar Duo+")
    offer = _offer(session, retailers["sephora"], "La Roche-Posay Effaclar Duo+M 40ml")
    match_offer(session, offer)
    assert match_offer(session, offer).method is MatchMethod.AWAITING_REVIEW
    assert len(_pending(session, offer)) == 1


def test_ean_match_clears_pending_candidates(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    _product(session, "Effaclar Duo+")
    offer = _offer(session, retailers["sephora"], "La Roche-Posay Effaclar Duo+M 40ml")
    match_offer(session, offer)
    duo_m = _product(session, "Effaclar Duo+M", ean=EAN_A)
    offer.ean = EAN_A  # the retailer started publishing the GTIN
    assert match_offer(session, offer).product is duo_m
    assert _pending(session, offer) == []


def test_candidate_pair_is_unique(session: Session, retailers: dict[str, Retailer]) -> None:
    product = _product(session, "Effaclar Duo+")
    offer = _offer(session, retailers["notino"], "x")
    session.add(MatchCandidate(offer=offer, product=product, score=80.0, reason="r"))
    session.flush()
    session.add(MatchCandidate(offer=offer, product=product, score=81.0, reason="r"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_match_unmatched_links_offers_across_retailers(
    session: Session, retailers: dict[str, Retailer]
) -> None:
    """End to end: the first retailer's listing creates the product, later retailers'
    listings of the same item join it (by EAN or name), a variant waits for review."""
    notino = _offer(
        session,
        retailers["notino"],
        "L'Oréal Paris Revitalift Filler ser cu acid hialuronic 30 ml",
        brand="L'Oréal Paris",
        ean=EAN_B,
    )
    emag = _offer(
        session,
        retailers["emag"],
        "Ser L’Oreal Paris Revitalift Filler acid hialuronic, 30ml -15%",
        brand="L'Oreal",
    )
    drmax = _offer(
        session,
        retailers["drmax"],
        "Ser antirid Revitalift Filler",  # different wording, same GTIN
        brand="Loreal Paris",
        ean=EAN_B,
    )
    variant = _offer(
        session,
        retailers["sephora"],
        "L'Oréal Paris Revitalift Filler ser cu acid hialuronic 50 ml",
        brand="L'Oréal Paris",
    )
    unbranded = _offer(session, retailers["emag"], "Ser facial 30 ml", brand=None)

    counts = match_unmatched(session)

    assert counts == {"new_product": 2, "fuzzy": 1, "ean": 1, "unmatched": 1}
    assert notino.product is not None
    assert emag.product is notino.product
    assert drmax.product is notino.product
    assert variant.product is not None and variant.product is not notino.product
    assert unbranded.product is None
    assert len(session.scalars(select(Product)).all()) == 2
    # A second run has nothing new to do.
    assert match_unmatched(session) == {"unmatched": 1}
