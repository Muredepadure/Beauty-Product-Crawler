"""Human review of ambiguous matches (the `match_candidates` table).

- `approve_candidate`: link the offer to the candidate's product; the offer's other
  pending candidates are rejected (an offer is one product).
- `reject_candidate`: mark the pair as different products. When it was the offer's last
  pending candidate, the offer is matched again (by default), which links it elsewhere
  or creates a new product, so a rejected offer isn't left orphaned.

Rejected pairs are remembered; the matcher never proposes them again.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from beautycrawler.db.base import utcnow
from beautycrawler.db.models import MatchCandidate, Offer
from beautycrawler.matching.service import (
    DEFAULT_CONFIG,
    MatchConfig,
    MatchResult,
    link_offer,
    match_offer,
)


class ReviewError(Exception):
    """A review action that can't be applied (unknown id, already decided, ...)."""


@dataclass(frozen=True, slots=True)
class RejectResult:
    candidate: MatchCandidate
    rematch: MatchResult | None  # set when the offer was matched again


def list_candidates(
    session: Session, status: str | None = "pending", limit: int | None = None
) -> list[MatchCandidate]:
    """Candidates (all when `status` is None), grouped by offer, best score first."""
    query = select(MatchCandidate).options(
        joinedload(MatchCandidate.offer).joinedload(Offer.retailer),
        joinedload(MatchCandidate.product),
    )
    if status is not None:
        query = query.where(MatchCandidate.status == status)
    query = query.order_by(MatchCandidate.offer_id, MatchCandidate.score.desc(), MatchCandidate.id)
    if limit is not None:
        query = query.limit(limit)
    return list(session.scalars(query).unique())


def _get(session: Session, candidate_id: int) -> MatchCandidate:
    candidate = session.get(MatchCandidate, candidate_id)
    if candidate is None:
        raise ReviewError(f"no match candidate with id {candidate_id}")
    return candidate


def approve_candidate(session: Session, candidate_id: int) -> MatchCandidate:
    """Link the candidate's offer to its product. Flushes; does not commit."""
    candidate = _get(session, candidate_id)
    if candidate.status != "pending":
        raise ReviewError(f"candidate {candidate_id} is already {candidate.status}")
    offer = candidate.offer
    if offer.product_id is not None and offer.product_id != candidate.product_id:
        raise ReviewError(
            f"offer {offer.id} is already linked to product {offer.product_id}; "
            "unlink it before approving another product"
        )
    now = utcnow()
    siblings = session.scalars(
        select(MatchCandidate).where(
            MatchCandidate.offer_id == offer.id,
            MatchCandidate.status == "pending",
            MatchCandidate.id != candidate.id,
        )
    )
    for other in siblings:
        other.status, other.decided_at = "rejected", now
    candidate.status, candidate.decided_at = "approved", now
    session.flush()
    link_offer(session, offer, candidate.product)
    session.flush()
    return candidate


def reject_candidate(
    session: Session,
    candidate_id: int,
    *,
    rematch: bool = True,
    config: MatchConfig = DEFAULT_CONFIG,
) -> RejectResult:
    """Mark a candidate as a different product. Flushes; does not commit."""
    candidate = _get(session, candidate_id)
    if candidate.status != "pending":
        raise ReviewError(f"candidate {candidate_id} is already {candidate.status}")
    candidate.status, candidate.decided_at = "rejected", utcnow()
    session.flush()
    offer = candidate.offer
    still_pending = session.scalars(
        select(MatchCandidate.id).where(
            MatchCandidate.offer_id == offer.id, MatchCandidate.status == "pending"
        )
    ).first()
    if not rematch or still_pending is not None or offer.product_id is not None:
        return RejectResult(candidate, None)
    return RejectResult(candidate, match_offer(session, offer, config))
