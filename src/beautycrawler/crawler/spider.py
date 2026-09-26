"""The common interface every retailer spider implements.

A spider has two jobs:

- `discover()` yields product-page URLs, by default from the site's XML sitemaps
  (those listed in robots.txt, plus `sitemap_urls`), filtered by `is_product_url()`.
  Spiders for sites without useful sitemaps override it to walk category listings.
- `parse_product(html, url)` turns one product page into `ScrapedOffer`s: usually one,
  several when a page lists variants (sizes/shades) with their own prices, none when the
  page isn't a product. It must be pure (no I/O) so it can be tested on saved fixtures.

`crawl()` glues them together through the shared `PoliteFetcher`.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import ClassVar

from beautycrawler.crawler.fetcher import FetchError, PoliteFetcher
from beautycrawler.crawler.scraped import ScrapedOffer
from beautycrawler.crawler.sitemap import parse_sitemap
from beautycrawler.extractors.jsonld import extract_products, to_scraped_offers

log = logging.getLogger(__name__)

MAX_SITEMAP_DEPTH = 3


@dataclass(slots=True)
class CrawlStats:
    pages_fetched: int = 0
    offers: int = 0
    pages_without_offers: int = 0
    errors: list[str] = field(default_factory=list)


class Spider(ABC):
    slug: ClassVar[str]  # matches Retailer.slug
    name: ClassVar[str]
    base_url: ClassVar[str]  # e.g. "https://www.notino.ro"
    sitemap_urls: ClassVar[tuple[str, ...]] = ()  # used in addition to robots.txt Sitemap:

    def __init__(self, fetcher: PoliteFetcher) -> None:
        self.fetcher = fetcher

    # ------------------------------------------------------------ to implement

    @abstractmethod
    def parse_product(self, html: str, url: str) -> list[ScrapedOffer]:
        """Offers on this product page ([] if it isn't one). No I/O."""

    def is_product_url(self, url: str) -> bool:
        """Whether a sitemap URL is a product page. Override per site."""
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
            if sitemap_url in seen_sitemaps or depth > MAX_SITEMAP_DEPTH:
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
        async for url in self.discover(limit=limit):
            try:
                result = await self.fetcher.fetch(url)
            except FetchError as exc:
                stats.errors.append(str(exc))
                log.warning("%s: %s", self.slug, exc)
                continue
            stats.pages_fetched += 1
            if not result.ok:
                stats.errors.append(f"{url}: HTTP {result.status_code}")
                continue
            try:
                offers = self.parse_product(result.text, result.url)
            except Exception as exc:  # a parser bug on one page must not end the crawl
                stats.errors.append(f"{url}: parse error: {exc!r}")
                log.exception("%s: parse error on %s", self.slug, url)
                continue
            if not offers:
                stats.pages_without_offers += 1
            for offer in offers:
                stats.offers += 1
                yield offer


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
