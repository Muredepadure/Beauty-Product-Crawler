"""Shared base for Shopify stores.

Shopify shops share one layout: robots.txt lists `/sitemap.xml`, an index of numbered
`sitemap_products_<n>.xml?from=…&to=…` sitemaps next to page, collection and blog
sitemaps (skipped). Product pages live at `/products/<handle>` and carry a `Product`
JSON-LD block with one `Offer` per variant.

Some themes cut the JSON-LD `name` short (Beauty Lounge: "… Pentru Par Deteriora"), so
when the page's `<h1>` continues the JSON-LD name it is used instead.
"""

import re
from typing import ClassVar
from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from beautycrawler.crawler.scraped import ScrapedOffer
from beautycrawler.crawler.spider import JsonLdSpider

_WANTED_SITEMAP = re.compile(r"^/(?:sitemap\.xml|sitemap_products_\d+\.xml)$")
# Only the default-language path: `/en/products/…` would duplicate every product.
_PRODUCT_PATH = re.compile(r"^/products/[^/]+/?$")


def _squash(text: str) -> str:
    return " ".join(text.split())


class ShopifySpider(JsonLdSpider):
    """Subclasses set `slug`, `name`, `base_url` and `hosts` (accepted netlocs)."""

    hosts: ClassVar[frozenset[str]]

    def is_wanted_sitemap(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.netloc.lower() in self.hosts and bool(_WANTED_SITEMAP.match(parts.path))

    def is_product_url(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.netloc.lower() in self.hosts and bool(_PRODUCT_PATH.match(parts.path))

    def parse_product(self, html: str, url: str) -> list[ScrapedOffer]:
        offers = super().parse_product(html, url)
        if not offers:
            return []
        h1 = HTMLParser(html).css_first("h1")
        heading = _squash(h1.text()) if h1 else ""
        return [
            offer.model_copy(update={"title": heading})
            if len(heading) > len(title := _squash(offer.title)) and heading.startswith(title)
            else offer
            for offer in offers
        ]
