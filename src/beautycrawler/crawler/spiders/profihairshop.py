"""Profihairshop (www.profihairshop.ro): professional hair and body care.

Audit (2026-10-18): robots.txt allows everything but asks for `Crawl-delay: 10`, which
the shared `PoliteFetcher` honours (one request per 10 s: a full crawl of ~1 300
products takes about 3.6 hours). `profihairshop.ro` redirects to `www.`; the fetcher
follows the redirect for robots.txt and checks robots.txt on every hop.

Product pages carry a complete schema.org `Product` JSON-LD block (name, price,
availability, GTIN, brand, image), so the generic JSON-LD parser is enough.

Discovery: the brand pages come first, because the products sitemap is out of date
(checked 2026-11-05: 146 of 179 L'Oreal Professionnel products were missing from it, and
many URLs it lists answer 404). `brands-sitemap.xml` lists the brand pages `/marci/<brand>`,
paginated with `?page=N&per-page=24`; each result is a `.product-card`. With a brand filter
only those brands' pages are walked. Without one the sitemap index follows, for products
no brand page shows: `products-sitemap.xml` next to page and category sitemaps, which are
skipped. Product URLs nest under their category path (`/par/vopsele-oxidanti/<slug>`,
`/seturi-cadou/<slug>`), so they look like category URLs: only URLs from the products
sitemap or a product card are treated as products.

The sitemap and the product's own JSON-LD don't always agree on the category path
(sitemap `/copii/<slug>`, JSON-LD `/copii/seturi-manichiura/<slug>`); the offer is
stored under the JSON-LD URL, so pages are recognised across runs by their last path
segment (the product slug) — see `page_key`.
"""

import logging
import re
from collections.abc import AsyncIterator
from urllib.parse import urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from beautycrawler.crawler.fetcher import FetchError
from beautycrawler.crawler.sitemap import parse_sitemap
from beautycrawler.crawler.spider import JsonLdSpider, register

log = logging.getLogger(__name__)

_HOSTS = frozenset({"www.profihairshop.ro", "profihairshop.ro"})
_WANTED_SITEMAPS = frozenset({"/sitemap-index.xml", "/products-sitemap.xml"})
_BRAND_PAGE_PATH = re.compile(r"^/marci/([^/]+)$")
_PAGE_NUMBER = re.compile(r"[?&]page=(\d+)")
PER_PAGE = 24


def parse_brand_page(html: str, page_url: str) -> tuple[list[str], int]:
    """Product URLs on a brand page, and the highest result page it links to (1 if none).
    Sort links are left out. No I/O."""
    tree = HTMLParser(html)
    urls = [
        urljoin(page_url, href)
        for link in tree.css(".product-card h3 a")
        if (href := link.attributes.get("href"))
    ]
    pages = [
        int(match.group(1))
        for link in tree.css('a[href*="page="]')
        if "sort=" not in (href := link.attributes.get("href") or "")
        and (match := _PAGE_NUMBER.search(href))
    ]
    return urls, max(pages, default=1)


@register
class ProfihairshopSpider(JsonLdSpider):
    slug = "profihairshop"
    name = "Profihairshop"
    base_url = "https://www.profihairshop.ro"
    sitemap_urls = (f"{base_url}/sitemap-index.xml",)

    def is_wanted_sitemap(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.netloc.lower() in _HOSTS and parts.path in _WANTED_SITEMAPS

    def is_product_url(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.netloc.lower() in _HOSTS and parts.path.strip("/") != ""

    def page_key(self, url: str) -> str:
        parts = urlsplit(url)
        slug = parts.path.rstrip("/").rsplit("/", 1)[-1].lower()
        return f"profihairshop:{slug}"

    async def _brand_pages(self) -> list[str]:
        """The wanted brands' pages, from the brands sitemap ([] if it can't be read)."""
        url = f"{self.base_url}/brands-sitemap.xml"
        try:
            result = await self.fetcher.fetch(url)
        except FetchError as exc:
            log.warning("%s: brand sitemap skipped: %s", self.slug, exc)
            return []
        if not result.ok:
            log.warning("%s: %s -> HTTP %s", self.slug, url, result.status_code)
            return []
        pages = []
        for page in parse_sitemap(result.content or result.text.encode()).urls:
            match = _BRAND_PAGE_PATH.match(urlsplit(page).path)
            if match and self.names_wanted_brand(match.group(1)):
                pages.append(page)
        return pages

    async def _brand_page_products(self, brand_page: str) -> AsyncIterator[str]:
        """Product URLs on every result page of one brand."""
        number, last = 1, 1
        while number <= last:
            url = f"{brand_page}?page={number}&per-page={PER_PAGE}"
            try:
                result = await self.fetcher.fetch(url)
            except FetchError as exc:
                log.warning("%s: brand page skipped: %s", self.slug, exc)
                return
            if not result.ok:
                log.warning("%s: %s -> HTTP %s", self.slug, url, result.status_code)
                return
            products, highest = parse_brand_page(result.text, result.url)
            for product in products:
                yield product
            last = max(last, highest)
            number += 1

    async def discover(self, limit: int | None = None) -> AsyncIterator[str]:
        seen: set[str] = set()
        count = 0
        for brand_page in await self._brand_pages():
            async for url in self._brand_page_products(brand_page):
                key = self.page_key(url)
                if key in seen:
                    continue
                seen.add(key)
                if key in self.skip_urls:
                    self.skipped_seen += 1
                    continue
                yield url
                count += 1
                if limit is not None and count >= limit:
                    return
        if self.brands:
            return  # the sitemap's stale URLs would add nothing to the brand pages
        async for url in super().discover():
            key = self.page_key(url)
            if key in seen:
                continue
            seen.add(key)
            yield url
            count += 1
            if limit is not None and count >= limit:
                return
