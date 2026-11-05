"""Coverage checks: is the database complete, and is the overlap between shops real?

`site_coverage` compares what a shop's site lists right now (the spider's own discovery,
no product page is fetched) with the listings in the database. `barcode_overlap` compares
two shops by barcode: a barcode found at both that isn't on one product means a matching
problem; few shared barcodes with good site coverage means the shops really differ.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from beautycrawler.crawler.spider import Spider
from beautycrawler.db.models import Offer, Retailer


@dataclass(slots=True)
class SiteCoverage:
    retailer: str
    on_site: int
    collected: int  # listed on the site and in the database
    missing: list[str] = field(default_factory=list)  # on the site, not in the database

    @property
    def percent(self) -> float:
        return 100.0 * self.collected / self.on_site if self.on_site else 100.0

    def line(self) -> str:
        return (
            f"{self.retailer}: {self.on_site} on the site, {self.collected} collected "
            f"({self.percent:.0f}%), {len(self.missing)} missing"
        )


@dataclass(slots=True)
class BarcodeOverlap:
    first: str
    second: str
    shared: int  # barcodes listed by both shops
    linked: int  # ... with both listings on one product
    unlinked: int  # ... on different products, or not linked yet

    def line(self) -> str:
        return (
            f"{self.first} + {self.second}: {self.shared} shared barcodes, "
            f"{self.linked} linked to one product, {self.unlinked} not linked"
        )


async def site_coverage(spider: Spider, session: Session) -> SiteCoverage:
    """Pages the spider finds on the site against this retailer's stored listings."""
    stored = session.scalars(
        select(Offer.url).join(Retailer).where(Retailer.slug == spider.slug)
    ).all()
    keys = {spider.page_key(url) for url in stored}
    on_site = 0
    missing: list[str] = []
    async for url in spider.discover():
        on_site += 1
        if spider.page_key(url) not in keys:
            missing.append(url)
    return SiteCoverage(spider.slug, on_site, on_site - len(missing), missing)


def barcode_overlap(session: Session, first: str, second: str) -> BarcodeOverlap:
    """Barcodes listed by both retailers, and whether they share a product."""
    a, b = aliased(Offer), aliased(Offer)
    ra, rb = aliased(Retailer), aliased(Retailer)
    rows = session.execute(
        select(a.ean, a.product_id, b.product_id)
        .join(ra, a.retailer_id == ra.id)
        .join(b, a.ean == b.ean)
        .join(rb, b.retailer_id == rb.id)
        .where(ra.slug == first, rb.slug == second, a.ean.is_not(None), a.ean != "")
    ).all()
    linked: dict[str | None, bool] = {}
    for ean, product_a, product_b in rows:
        same = product_a is not None and product_a == product_b
        linked[ean] = linked.get(ean, False) or same
    together = sum(linked.values())
    return BarcodeOverlap(first, second, len(linked), together, len(linked) - together)
