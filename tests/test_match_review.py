"""P4.5: reviewing ambiguous matches (service functions and the admin CLI)."""

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from beautycrawler.db import Base
from beautycrawler.db.models import Brand, MatchCandidate, Offer, Product, Retailer
from beautycrawler.db.session import make_engine, make_session_factory
from beautycrawler.matching.__main__ import main
from beautycrawler.matching.review import (
    ReviewError,
    approve_candidate,
    list_candidates,
    reject_candidate,
)
from beautycrawler.matching.service import MatchMethod, match_offer

EAN = "5901234123457"


def _setup(session: Session) -> tuple[Product, Product, Offer]:
    """Two same-size Hydrating Cleanser products and an offer close to both, so the
    matcher files two pending candidates for it."""
    retailer = Retailer(slug="emag", name="eMAG", domain="emag.ro")
    brand = Brand(name="CeraVe", normalized_name="cerave")
    a = Product(
        brand=brand,
        name="Hydrating Cleanser",
        normalized_name="hydrating cleanser",
        size_value=Decimal(236),
        size_unit="ml",
    )
    b = Product(
        brand=brand,
        name="Hydrating Cleanser gel",
        normalized_name="hydrating cleanser gel",
        size_value=Decimal(236),
        size_unit="ml",
    )
    offer = Offer(
        retailer=retailer,
        url="https://emag.ro/p/1",
        title="CeraVe Hydrating Cleanser 236 ml",
        brand_name="CeraVe",
        ean=EAN,
        price_bani=5_999,
        in_stock=True,
    )
    session.add_all([a, b, offer])
    session.flush()
    assert match_offer(session, offer).method is MatchMethod.REVIEW
    return a, b, offer


def _candidate(session: Session, offer: Offer, product: Product) -> MatchCandidate:
    return session.scalars(
        select(MatchCandidate).where(
            MatchCandidate.offer_id == offer.id, MatchCandidate.product_id == product.id
        )
    ).one()


# --- service -----------------------------------------------------------------------


def test_list_candidates_grouped_best_first(session: Session) -> None:
    a, b, _ = _setup(session)
    rows = list_candidates(session)
    assert [r.product_id for r in rows] == [a.id, b.id]  # exact name scores higher
    assert rows[0].score >= rows[1].score
    assert list_candidates(session, "approved") == []
    assert len(list_candidates(session, None)) == 2
    assert len(list_candidates(session, limit=1)) == 1


def test_approve_links_offer_and_rejects_siblings(session: Session) -> None:
    a, b, offer = _setup(session)
    approve_candidate(session, _candidate(session, offer, a).id)
    assert offer.product is a
    assert a.ean == EAN  # learned from the offer
    assert _candidate(session, offer, a).status == "approved"
    sibling = _candidate(session, offer, b)
    assert sibling.status == "rejected" and sibling.decided_at is not None


def test_approve_twice_is_an_error(session: Session) -> None:
    a, _, offer = _setup(session)
    cid = _candidate(session, offer, a).id
    approve_candidate(session, cid)
    with pytest.raises(ReviewError, match="already approved"):
        approve_candidate(session, cid)


def test_approve_unknown_id_is_an_error(session: Session) -> None:
    with pytest.raises(ReviewError, match="no match candidate"):
        approve_candidate(session, 999)


def test_approve_refuses_offer_linked_elsewhere(session: Session) -> None:
    a, b, offer = _setup(session)
    offer.product = b
    session.flush()
    with pytest.raises(ReviewError, match="already linked"):
        approve_candidate(session, _candidate(session, offer, a).id)


def test_reject_keeps_offer_waiting_while_other_candidates_pending(session: Session) -> None:
    a, b, offer = _setup(session)
    result = reject_candidate(session, _candidate(session, offer, a).id)
    assert result.rematch is None
    assert offer.product is None
    assert _candidate(session, offer, b).status == "pending"


def test_rejecting_last_candidate_rematches_offer(session: Session) -> None:
    a, b, offer = _setup(session)
    reject_candidate(session, _candidate(session, offer, a).id)
    result = reject_candidate(session, _candidate(session, offer, b).id)
    assert result.rematch is not None
    assert result.rematch.method is MatchMethod.NEW_PRODUCT
    new = offer.product
    assert new is not None and new not in (a, b)
    assert (new.name, new.ean) == ("Hydrating Cleanser", EAN)
    # the rejected pairs are not proposed again on later runs
    assert match_offer(session, offer).method is MatchMethod.ALREADY_LINKED
    assert {c.status for c in list_candidates(session, None)} == {"rejected"}


def test_reject_without_rematch_leaves_offer_unmatched(session: Session) -> None:
    a, b, offer = _setup(session)
    reject_candidate(session, _candidate(session, offer, a).id, rematch=False)
    result = reject_candidate(session, _candidate(session, offer, b).id, rematch=False)
    assert result.rematch is None
    assert offer.product is None


# --- CLI ---------------------------------------------------------------------------


@pytest.fixture
def db_url(tmp_path: Path) -> Iterator[str]:
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    yield url


@pytest.fixture
def file_engine(db_url: str) -> Iterator[Engine]:
    engine = make_engine(db_url)
    yield engine
    engine.dispose()


def _seed_offers(engine: Engine) -> None:
    """Two products and an unmatched offer close to both (review), plus a clean offer."""
    with make_session_factory(engine)() as s:
        retailer = Retailer(slug="emag", name="eMAG", domain="emag.ro")
        brand = Brand(name="CeraVe", normalized_name="cerave")
        for name in ("Hydrating Cleanser", "Hydrating Cleanser gel"):
            s.add(
                Product(
                    brand=brand,
                    name=name,
                    normalized_name=name.lower(),
                    size_value=Decimal(236),
                    size_unit="ml",
                )
            )
        for i, title in enumerate(
            ["CeraVe Hydrating Cleanser 236 ml", "CeraVe Moisturising Cream 340 g"]
        ):
            s.add(
                Offer(
                    retailer=retailer,
                    url=f"https://emag.ro/p/{i}",
                    title=title,
                    brand_name="CeraVe",
                    price_bani=5_999,
                    in_stock=True,
                )
            )
        s.commit()


def _pending_ids(engine: Engine) -> list[int]:
    with make_session_factory(engine)() as s:
        return [c.id for c in list_candidates(s)]


def test_cli_run_list_approve(
    db_url: str, file_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_offers(file_engine)
    assert main(["--database-url", db_url, "run"]) == 0
    out = capsys.readouterr().out
    assert "new_product      1" in out and "review           1" in out

    assert main(["--database-url", db_url, "list"]) == 0
    out = capsys.readouterr().out
    assert "[emag] 'CeraVe Hydrating Cleanser 236 ml'" in out
    assert "CeraVe 'Hydrating Cleanser' (236 ml" in out
    assert "several close matches" in out

    best = _pending_ids(file_engine)[0]
    assert main(["--database-url", db_url, "approve", str(best)]) == 0
    assert f"Approved #{best}" in capsys.readouterr().out
    assert _pending_ids(file_engine) == []

    assert main(["--database-url", db_url, "list"]) == 0
    assert "No match candidates." in capsys.readouterr().out
    assert main(["--database-url", db_url, "list", "--status", "all"]) == 0
    out = capsys.readouterr().out
    assert "approved" in out and "rejected" in out


def test_cli_reject_rematches(
    db_url: str, file_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_offers(file_engine)
    main(["--database-url", db_url, "run"])
    ids = _pending_ids(file_engine)
    capsys.readouterr()
    assert main(["--database-url", db_url, "reject", *map(str, ids)]) == 0
    out = capsys.readouterr().out
    assert f"Rejected #{ids[0]}\n" in out
    assert "re-matched: new_product -> product" in out
    with make_session_factory(file_engine)() as s:
        assert s.scalars(select(Offer).where(Offer.product_id.is_(None))).all() == []


def test_cli_reject_is_all_or_nothing(
    db_url: str, file_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_offers(file_engine)
    main(["--database-url", db_url, "run"])
    ids = _pending_ids(file_engine)
    assert main(["--database-url", db_url, "reject", str(ids[0]), "999"]) == 1
    assert "no match candidate with id 999" in capsys.readouterr().err
    assert _pending_ids(file_engine) == ids


def test_cli_run_without_offers_and_no_create(
    db_url: str, file_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--database-url", db_url, "run"]) == 0
    assert "No unmatched offers." in capsys.readouterr().out
    _seed_offers(file_engine)
    assert main(["--database-url", db_url, "run", "--no-create"]) == 0
    assert "unmatched        1" in capsys.readouterr().out


def test_cli_rejects_bad_limit(db_url: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--database-url", db_url, "run", "--limit", "0"]) == 2
    assert "--limit" in capsys.readouterr().err
