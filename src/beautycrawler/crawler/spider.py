"""The common interface every retailer spider implements.

A spider has two jobs:

- `discover()` yields product-page URLs, by default from the site's XML sitemaps
  (those listed in robots.txt, plus `sitemap_urls`), filtered by `is_product_url()`.
  Spiders for sites without useful sitemaps override it to walk category listings.
- `parse_product(html, url)` turns one product page into `ScrapedOffer`s: usually one,
  several when a page lists variants (sizes/shades) with their own prices, none when the
  page isn't a product. It must be pure (no I/O) so it can be tested on saved fixtures.

`crawl()` glues them together through the shared `PoliteFetcher`.

Long catalogues are crawled over several runs (e.g. one per night): `skip_urls` holds
pages already seen recently (they are left out of discovery, so `limit` counts only new
work), `deadline` stops the crawl between pages at a set time, and a shop that keeps
answering 429 after the fetcher's retries is given up for this run. A crawl cut short
for any of these reasons sets `CrawlStats.stopped`.

`brands` limits a crawl to some brands: a product URL whose last path segment names none
of them is never fetched, and a parsed offer whose brand names none of them is dropped
(an offer without a brand is kept, its URL already matched). Brands are compared as
`brand_token`s, so "l-oreal", "L`OREAL PROFESSIONNEL" and "Kérastase" all match.
"""

import logging
import re
import time
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import ClassVar
from urllib.parse import urlsplit, urlunsplit

from beautycrawler.crawler.fetcher import FetchError, PoliteFetcher
from beautycrawler.crawler.scraped import ScrapedOffer
from beautycrawler.crawler.sitemap import parse_sitemap
from beautycrawler.extractors.jsonld import extract_products, to_scraped_offers

log = logging.getLogger(__name__)

MAX_SITEMAP_DEPTH = 3
# Pages in a row still answered 429 after the fetcher's retries before the shop is given
# up for this run (its rate limit isn't going to lift while we keep asking).
RATE_LIMIT_GIVE_UP_AFTER = 5


def page_key(url: str) -> str:
    """URL without query, fragment and trailing slash, to recognise a page across runs
    (offers may be stored as `…/products/x?variant=1` or `…#sku=…`).

    Skipping seen pages relies on a shop storing offers under its page URL (true for every
    current spider); where the product data names another URL, pages are simply crawled
    again, which costs time but never loses data."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


@dataclass(slots=True)
class CrawlStats:
    pages_fetched: int = 0
    offers: int = 0
    pages_without_offers: int = 0
    errors: list[str] = field(default_factory=list)
    skipped_seen: int = 0  # product URLs left out because they were seen recently
    skipped_brands: int = 0  # product URLs/offers left out by the `brands` filter
    stopped: str | None = None  # why the crawl ended early (time limit, rate limited)


def brand_token(text: str) -> str:
    """Lowercase ASCII letters and digits only: "L`Oréal Professionnel" -> "lorealprofessionnel"."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())


class Spider(ABC):
    slug: ClassVar[str]  # matches Retailer.slug
    name: ClassVar[str]
    base_url: ClassVar[str]  # e.g. "https://www.notino.ro"
    sitemap_urls: ClassVar[tuple[str, ...]] = ()  # used in addition to robots.txt Sitemap:

    def __init__(
        self,
        fetcher: PoliteFetcher,
        *,
        skip_urls: frozenset[str] = frozenset(),
        deadline: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        brands: tuple[str, ...] = (),
    ) -> None:
        self.fetcher = fetcher
        self.brands = tuple(brand_token(b) for b in brands if brand_token(b))
        self.skip_urls = skip_urls  # self.page_key()s of pages not to fetch this run
        self.deadline = deadline  # `clock()` value after which no new page is fetched
        self.clock = clock
        self.skipped_seen = 0
        self.skipped_brands = 0

    # ------------------------------------------------------------ to implement

    @abstractmethod
    def parse_product(self, html: str, url: str) -> list[ScrapedOffer]:
        """Offers on this product page ([] if it isn't one). No I/O."""

    def is_product_url(self, url: str) -> bool:
        """Whether a sitemap URL is a product page. Override per site."""
        return True

    def page_key(self, url: str) -> str:
        """Key that recognises a product page across runs, comparing the sitemap URL with
        the URL the offer was stored under. Override when a shop's product data names a
        different URL than its sitemap (Profihairshop adds a category level)."""
        return page_key(url)

    def names_wanted_brand(self, text: str | None) -> bool:
        """Whether `text` (a URL slug or brand name) names one of `brands` (always True
        without a brand filter)."""
        if not self.brands:
            return True
        token = brand_token(text or "")
        return any(b in token for b in self.brands)

    def is_wanted_sitemap(self, url: str) -> bool:
        """Whether to fetch this sitemap (root or child). Override to skip image, review
        or blog sitemaps that never list product pages."""
        return True

    # ------------------------------------------------------------ discovery

    async def discover(self, limit: int | None = None) -> AsyncIterator[str]:
        """Product URLs from sitemaps, deduplicated, at most `limit`."""
        roots = [*await self.fetcher.sitemaps(self.base_url), *self.sitemap_urls]
        seen_sitemaps: set[str] = set()
        seen_urls: set[str] = set()
        count = 0
        stack: list[tuple[str, int]] = [(u, 0) for u in reversed(dict.fromkeys(roots))]
        while stack:
            sitemap_url, depth = stack.pop()
            if (
                sitemap_url in seen_sitemaps
                or depth > MAX_SITEMAP_DEPTH
                or not self.is_wanted_sitemap(sitemap_url)
            ):
                continue
            seen_sitemaps.add(sitemap_url)
            try:
                result = await self.fetcher.fetch(sitemap_url)
            except FetchError as exc:
                log.warning("%s: sitemap skipped: %s", self.slug, exc)
                continue
            if not result.ok:
                log.warning("%s: sitemap %s -> HTTP %s", self.slug, sitemap_url, result.status_code)
                continue
            sitemap = parse_sitemap(result.content or result.text.encode())
            stack.extend((u, depth + 1) for u in reversed(sitemap.sitemaps))
            for url in sitemap.urls:
                if url in seen_urls or not self.is_product_url(url):
                    continue
                seen_urls.add(url)
                slug = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
                if not self.names_wanted_brand(slug):
                    self.skipped_brands += 1
                    continue
                if self.skip_urls and self.page_key(url) in self.skip_urls:
                    self.skipped_seen += 1
                    continue
                yield url
                count += 1
                if limit is not None and count >= limit:
                    return

    # ------------------------------------------------------------ crawling

    async def crawl(
        self, limit: int | None = None, stats: CrawlStats | None = None
    ) -> AsyncIterator[ScrapedOffer]:
        """Discover product pages, fetch and parse them. Errors are logged and counted
        in `stats`, never raised, so one bad page doesn't stop the run."""
        stats = stats if stats is not None else CrawlStats()
        rate_limited_in_a_row = 0
        try:
            async for url in self.discover(limit=limit):
                if self.deadline is not None and self.clock() >= self.deadline:
                    stats.stopped = "time limit reached"
                    log.info("%s: stopping, time limit reached", self.slug)
                    return
                try:
                    result = await self.fetcher.fetch(url)
                except FetchError as exc:
                    stats.errors.append(str(exc))
                    log.warning("%s: %s", self.slug, exc)
                    continue
                stats.pages_fetched += 1
                if result.status_code == 429:
                    rate_limited_in_a_row += 1
                    stats.errors.append(f"{url}: HTTP 429")
                    if rate_limited_in_a_row >= RATE_LIMIT_GIVE_UP_AFTER:
                        stats.stopped = (
                            f"rate limited ({rate_limited_in_a_row} pages in a row answered 429)"
                        )
                        log.warning("%s: giving up for this run: %s", self.slug, stats.stopped)
                        return
                    continue
                rate_limited_in_a_row = 0
                if not result.ok:
                    stats.errors.append(f"{url}: HTTP {result.status_code}")
                    continue
                for offer in self._parse(url, result.text, result.url, stats):
                    yield offer
        finally:
            stats.skipped_seen = self.skipped_seen
            stats.skipped_brands = self.skipped_brands

    def _parse(self, url: str, text: str, final_url: str, stats: CrawlStats) -> list[ScrapedOffer]:
        try:
            offers = self.parse_product(text, final_url)
        except Exception as exc:  # a parser bug on one page must not end the crawl
            stats.errors.append(f"{url}: parse error: {exc!r}")
            log.exception("%s: parse error on %s", self.slug, url)
            return []
        if self.brands:
            wanted = [o for o in offers if o.brand is None or self.names_wanted_brand(o.brand)]
            self.skipped_brands += len(offers) - len(wanted)
            offers = wanted
        if not offers:
            stats.pages_without_offers += 1
        stats.offers += len(offers)
        return offers


class JsonLdSpider(Spider):
    """A spider whose product pages carry complete schema.org JSON-LD."""

    def parse_product(self, html: str, url: str) -> list[ScrapedOffer]:
        return to_scraped_offers(extract_products(html), retailer=self.slug, page_url=url)


# ------------------------------------------------------------------ registry

_REGISTRY: dict[str, type[Spider]] = {}


def register[S: type[Spider]](cls: S) -> S:
    """Class decorator adding a spider to the registry under its `slug`."""
    slug = cls.slug
    if slug in _REGISTRY and _REGISTRY[slug] is not cls:
        raise ValueError(f"duplicate spider slug {slug!r}")
    _REGISTRY[slug] = cls
    return cls


def get_spider(slug: str) -> type[Spider]:
    try:
        return _REGISTRY[slug]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "none"
        raise KeyError(f"unknown spider {slug!r} (registered: {known})") from None


def registered_spiders() -> dict[str, type[Spider]]:
    return dict(_REGISTRY)
