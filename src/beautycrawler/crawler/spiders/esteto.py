"""Esteto (www.esteto.ro): general store with cosmetics, perfume and salon supplies.

Audit (2026-10-18): robots.txt allows product pages (`/produse-<id>-<slug>`). Product
pages carry a complete `Product` JSON-LD block (GTIN often missing), so the generic
JSON-LD parser is enough.

Discovery: there is no sitemap (404), so products are found by walking category
listings. The home page links to every top-level category; only the beauty ones in
`categories` are walked (Esteto also sells clothes, books, toys and food, and the home
page's own product links mix all of them, so they are not used). From a
listing page the spider follows product links, links deeper into the same category
(subcategories) and pagination links (`?page=N` style, nothing else in the query, so
sort and filter combinations are never crawled). Listing pages are capped at
`max_listing_pages` per run, and every request goes through the polite fetcher
(robots.txt, delay).

The exact pagination format was not in the audit fixtures: confirm it with the first
live run (a listing page whose pagination isn't followed shows up as few products).
"""

import logging
import re
from collections import deque
from collections.abc import AsyncIterator
from typing import ClassVar
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from beautycrawler.crawler.fetcher import FetchError
from beautycrawler.crawler.spider import JsonLdSpider, register

log = logging.getLogger(__name__)

_HOST = "www.esteto.ro"
_PRODUCT_PATH = re.compile(r"^/produse-\d+-[^/]+$")
_PAGE_PARAMS = frozenset({"page", "p", "pagina"})


@register
class EstetoSpider(JsonLdSpider):
    slug = "esteto"
    name = "Esteto"
    base_url = f"https://{_HOST}"
    # Top-level category paths (as linked from the home page) whose products we track.
    categories: ClassVar[tuple[str, ...]] = ("/produse-cosmetice", "/parfumuri")
    max_listing_pages: ClassVar[int] = 2000

    def is_product_url(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.netloc.lower() == _HOST and bool(_PRODUCT_PATH.match(parts.path))

    def listing_url(self, url: str) -> str | None:
        """`url` normalized (no fragment) if it is a listing page of a tracked
        category or its pagination, else None."""
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or parts.netloc.lower() != _HOST:
            return None
        path = parts.path.rstrip("/") or "/"
        if not any(path == c or path.startswith(f"{c}/") for c in self.categories):
            return None
        query = parse_qsl(parts.query, keep_blank_values=True)
        if len(query) > 1 or any(k not in _PAGE_PARAMS or not v.isdigit() for k, v in query):
            return None
        return urlunsplit(("https", _HOST, path, parts.query, ""))

    def _links(self, html: str, page_url: str) -> list[str]:
        tree = HTMLParser(html)
        return [
            urljoin(page_url, href)
            for a in tree.css("a[href]")
            if (href := (a.attributes.get("href") or "").strip())
        ]

    async def _get_html(self, url: str) -> str | None:
        try:
            result = await self.fetcher.fetch(url)
        except FetchError as exc:
            log.warning("%s: listing skipped: %s", self.slug, exc)
            return None
        if not result.ok:
            log.warning("%s: listing %s -> HTTP %s", self.slug, url, result.status_code)
            return None
        return result.text

    async def discover(self, limit: int | None = None) -> AsyncIterator[str]:
        """Product URLs from the tracked categories' listings (breadth-first),
        deduplicated, at most `limit`."""
        seen_products: set[str] = set()
        seen_listings: set[str] = set()
        queue: deque[str] = deque()
        count = 0

        def take(links: list[str]) -> list[str]:
            new = []
            for link in links:
                product = urlunsplit(urlsplit(link)._replace(query="", fragment=""))
                if self.is_product_url(product):
                    if product not in seen_products:
                        seen_products.add(product)
                        new.append(product)
                elif (listing := self.listing_url(link)) and listing not in seen_listings:
                    seen_listings.add(listing)
                    queue.append(listing)
            return new

        take([f"{self.base_url}{category}" for category in self.categories])
        pages = 0
        while queue and pages < self.max_listing_pages:
            listing = queue.popleft()
            pages += 1
            html = await self._get_html(listing)
            if html is None:
                continue
            for url in take(self._links(html, listing)):
                yield url
                count += 1
                if limit is not None and count >= limit:
                    return
        if queue:
            log.warning(
                "%s: stopped after %d listing pages, %d not visited",
                self.slug,
                pages,
                len(queue),
            )
