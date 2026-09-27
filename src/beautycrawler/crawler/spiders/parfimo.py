"""Parfimo (parfimo.ro): perfumes, cosmetics and dermocosmetics.

Audit (2026-09-27): robots.txt allows everything except `/schimbare-date/` and the
GraphQL endpoints. Plain HTTP works (BunnyCDN, no bot wall). Product pages are
server-rendered with a schema.org `Product` JSON-LD block holding one `Offer` (price,
availability, GTIN); the size is part of the product name ("... 200 ml"). The JSON-LD
has no brand and no image, so those come from the page: the brand link in the product
heading (`h1 .producer-name`) and the first `product_detail` gallery photo.

Discovery: the sitemap index lists numbered product sitemaps
(`/<n>/sitemap_products.xml`, ~2 500 URLs each) next to article, producer, menu and
filter sitemaps, which are skipped. Product URLs end in `_z<id>/`.
"""

import re
from urllib.parse import urljoin, urlsplit

from selectolax.parser import HTMLParser

from beautycrawler.crawler.scraped import ScrapedOffer
from beautycrawler.crawler.spider import JsonLdSpider, register

_HOST = "www.parfimo.ro"
_WANTED_SITEMAP = re.compile(r"^/(?:sitemap\.xml|\d+/sitemap_products\.xml)$")
_PRODUCT_PATH = re.compile(r"^/[^/]+_z\d+/$")
_PHOTO = "/photo/product_detail/"


@register
class ParfimoSpider(JsonLdSpider):
    slug = "parfimo"
    name = "Parfimo"
    base_url = f"https://{_HOST}"

    def is_wanted_sitemap(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.netloc == _HOST and bool(_WANTED_SITEMAP.match(parts.path))

    def is_product_url(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.netloc == _HOST and bool(_PRODUCT_PATH.match(parts.path))

    def parse_product(self, html: str, url: str) -> list[ScrapedOffer]:
        offers = super().parse_product(html, url)
        if not offers:
            return []
        tree = HTMLParser(html)
        brand_node = tree.css_first("h1 .producer-name")
        brand = brand_node.text(strip=True) if brand_node else None
        image = next(
            (
                urljoin(url, src)
                for img in tree.css("img")
                if _PHOTO in (src := img.attributes.get("src") or "")
            ),
            None,
        )
        return [
            offer.model_copy(
                update={
                    "brand": offer.brand or brand or None,
                    "image_url": offer.image_url or image,
                }
            )
            for offer in offers
        ]
