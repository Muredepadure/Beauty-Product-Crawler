"""Link scraped offers to canonical products.

For each offer without a product, `match_offer` tries, in order:

1. **EAN/GTIN exact**: a product with the offer's EAN -> linked.
2. **Fuzzy**: products of the same brand are scored on their name keys
   (`matching.keys`). A product is excluded when its size or EAN contradicts the
   offer, or the names name different numbers (SPF 30 vs 50). The best candidate is
   linked automatically only when it is unambiguous: score >= `MatchConfig.auto_threshold`,
   both sizes known and equal, no variant-marker doubts, a single-item pack, and no
   runner-up within `ambiguity_margin`.
3. Otherwise candidates scoring >= `review_threshold` are written to the
   `match_candidates` review table (the offer stays unlinked until a human decides).
4. No candidate at all -> a new `Product` is created from the offer, when that is safe
   (brand known, not a multipack). Otherwise the offer is left unmatched.

Nothing is merged on a guess: when in doubt, it goes to review.
"""

import enum
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from beautycrawler.db.models import Brand, MatchCandidate, Offer, Product
from beautycrawler.matching.keys import (
    base_size,
    display_name,
    name_tokens,
    offer_size,
    score_pair,
)
from beautycrawler.normalization.brands import brand_key, canonical_brand
from beautycrawler.normalization.text import fold

MAX_CANDIDATES = 5  # review rows written per offer


class MatchMethod(enum.Enum):
    ALREADY_LINKED = "already_linked"
    EAN = "ean"
    FUZZY = "fuzzy"
    NEW_PRODUCT = "new_product"
    REVIEW = "review"
    AWAITING_REVIEW = "awaiting_review"  # has pending candidates from an earlier run
    UNMATCHED = "unmatched"


@dataclass(frozen=True, slots=True)
class MatchConfig:
    auto_threshold: float = 90.0
    review_threshold: float = 75.0
    ambiguity_margin: float = 3.0  # best must beat the runner-up by this much
    create_products: bool = True


DEFAULT_CONFIG = MatchConfig()


@dataclass(frozen=True, slots=True)
class Candidate:
    product: Product
    score: float
    doubts: tuple[str, ...] = ()


@dataclass(slots=True)
class MatchResult:
    offer: Offer
    method: MatchMethod
    product: Product | None = None
    candidates: list[Candidate] = field(default_factory=list)
    note: str | None = None


def _brand_for(session: Session, raw: str | None) -> Brand | None:
    name = canonical_brand(raw)
    if name is None:
        return None
    return session.scalars(
        select(Brand).where(Brand.normalized_name == brand_key(name))
    ).one_or_none()


def _get_or_create_brand(session: Session, raw: str) -> Brand:
    brand = _brand_for(session, raw)
    if brand is None:
        name = canonical_brand(raw) or raw
        brand = Brand(name=name, normalized_name=brand_key(name))
        session.add(brand)
        session.flush()
    return brand


def link_offer(session: Session, offer: Offer, product: Product) -> None:
    """Link and enrich the product with facts the offer knows and it doesn't."""
    offer.product = product
    if offer.id is not None:
        session.execute(
            delete(MatchCandidate).where(
                MatchCandidate.offer_id == offer.id, MatchCandidate.status == "pending"
            )
        )
    if product.ean is None and offer.ean is not None:
        taken = session.scalars(select(Product.id).where(Product.ean == offer.ean)).first()
        if taken is None:
            product.ean = offer.ean
    if product.image_url is None and offer.image_url is not None:
        product.image_url = offer.image_url


def _rejected_product_ids(session: Session, offer: Offer) -> set[int]:
    return set(
        session.scalars(
            select(MatchCandidate.product_id).where(
                MatchCandidate.offer_id == offer.id, MatchCandidate.status == "rejected"
            )
        )
    )


def _has_pending(session: Session, offer: Offer) -> bool:
    return (
        session.scalars(
            select(MatchCandidate.id).where(
                MatchCandidate.offer_id == offer.id, MatchCandidate.status == "pending"
            )
        ).first()
        is not None
    )


def find_candidates(
    session: Session, offer: Offer, review_threshold: float = DEFAULT_CONFIG.review_threshold
) -> tuple[list[Candidate], int]:
    """Same-brand products scoring >= `review_threshold`, best first, plus the offer's
    pack count. Products contradicting the offer (size, EAN, numbers) are excluded."""
    size, count = offer_size(offer.title, offer.size_value, offer.size_unit)
    brand = _brand_for(session, offer.brand_name)
    if brand is None:
        return [], count
    offer_key = name_tokens(offer.title, offer.brand_name)
    rejected = _rejected_product_ids(session, offer)
    candidates = []
    for product in session.scalars(select(Product).where(Product.brand_id == brand.id)):
        if product.id in rejected:
            continue
        if offer.ean and product.ean and offer.ean != product.ean:
            continue
        product_size = base_size(product.size_value, product.size_unit)
        doubts: list[str] = []
        if size is not None and product_size is not None:
            per_item_equal = size == product_size
            total_equal = count > 1 and (size[0] * count, size[1]) == product_size
            if not (per_item_equal or total_equal):
                continue
        else:
            doubts.append("size unknown")
        if count > 1:
            doubts.append(f"multipack of {count}")
        pair = score_pair(offer_key, name_tokens(product.name, brand.name))
        if pair.conflict is not None or pair.score < review_threshold:
            continue
        candidates.append(Candidate(product, pair.score, (*pair.doubts, *doubts)))
    candidates.sort(key=lambda c: (-c.score, c.product.id))
    return candidates, count


def _record_review(session: Session, offer: Offer, candidates: list[Candidate]) -> None:
    existing = {
        c.product_id: c
        for c in session.scalars(select(MatchCandidate).where(MatchCandidate.offer_id == offer.id))
    }
    for cand in candidates[:MAX_CANDIDATES]:
        reason = "; ".join(cand.doubts) or "close score"
        row = existing.get(cand.product.id)
        if row is None:
            session.add(
                MatchCandidate(
                    offer=offer,
                    product=cand.product,
                    score=round(cand.score, 2),
                    reason=reason[:500],
                )
            )
        elif row.status == "pending":
            row.score, row.reason = round(cand.score, 2), reason[:500]


def _new_product(session: Session, offer: Offer, size: tuple[Decimal, str] | None) -> Product:
    assert offer.brand_name is not None
    brand = _get_or_create_brand(session, offer.brand_name)
    name = display_name(offer.title, offer.brand_name)
    product = Product(
        brand=brand,
        name=name,
        normalized_name=fold(name),
        size_value=size[0] if size else None,
        size_unit=size[1] if size else None,
    )
    session.add(product)
    return product


def match_offer(
    session: Session,
    offer: Offer,
    config: MatchConfig = DEFAULT_CONFIG,
) -> MatchResult:
    """Match one offer (see module docstring). Flushes; does not commit."""
    if offer.product_id is not None or offer.product is not None:
        return MatchResult(offer, MatchMethod.ALREADY_LINKED, offer.product)

    if offer.ean:
        by_ean = session.scalars(select(Product).where(Product.ean == offer.ean)).one_or_none()
        if by_ean is not None:
            link_offer(session, offer, by_ean)
            session.flush()
            return MatchResult(offer, MatchMethod.EAN, by_ean)

    if offer.id is not None and _has_pending(session, offer):
        return MatchResult(offer, MatchMethod.AWAITING_REVIEW)

    candidates, count = find_candidates(session, offer, config.review_threshold)
    if candidates:
        best = candidates[0]
        runner_up = candidates[1].score if len(candidates) > 1 else None
        clear_winner = runner_up is None or best.score - runner_up >= config.ambiguity_margin
        confident = best.score >= config.auto_threshold and not best.doubts
        if confident and clear_winner:
            link_offer(session, offer, best.product)
            session.flush()
            return MatchResult(offer, MatchMethod.FUZZY, best.product, candidates)
        if confident:
            candidates = [
                Candidate(c.product, c.score, (*c.doubts, "several close matches"))
                for c in candidates
            ]
        session.flush()  # the offer needs an id for the review rows
        _record_review(session, offer, candidates)
        session.flush()
        return MatchResult(offer, MatchMethod.REVIEW, None, candidates)

    if not config.create_products:
        return MatchResult(offer, MatchMethod.UNMATCHED, note="no candidate")
    if not offer.brand_name or canonical_brand(offer.brand_name) is None:
        return MatchResult(offer, MatchMethod.UNMATCHED, note="brand unknown")
    if count > 1:
        # Product has no pack-count column yet; don't create "50 ml" for a 2 x 50 ml pack.
        return MatchResult(offer, MatchMethod.UNMATCHED, note=f"multipack of {count}")
    size, _ = offer_size(offer.title, offer.size_value, offer.size_unit)
    product = _new_product(session, offer, size)
    link_offer(session, offer, product)
    session.flush()
    return MatchResult(offer, MatchMethod.NEW_PRODUCT, product)


def match_unmatched(
    session: Session, config: MatchConfig = DEFAULT_CONFIG, *, limit: int | None = None
) -> Counter[str]:
    """Run `match_offer` over offers without a product, oldest first.

    Offers are processed one at a time, so an offer can match a product created from
    an earlier offer in the same run. Returns counts per `MatchMethod` value.
    """
    query = select(Offer).where(Offer.product_id.is_(None)).order_by(Offer.id)
    if limit is not None:
        query = query.limit(limit)
    counts: Counter[str] = Counter()
    for offer in session.scalars(query).all():
        result = match_offer(session, offer, config)
        counts[result.method.value] += 1
    return counts
