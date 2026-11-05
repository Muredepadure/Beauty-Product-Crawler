"""XpertBeauty (www.xpertbeauty.ro): professional skin, hair and nail care (Magento).

Audit (2026-10-18): robots.txt's `*` group only blocks filter URLs. There is no
top-level `Product` JSON-LD (the product is nested in an `ItemPage`, which the generic
extractor doesn't read), so this spider has its own parser built on what Magento
renders for every product page:

- the analytics block (`text/x-magento-init`, `Evx_DataReshape/js/events`) with a
  `product_viewed` event: id, name, price, price before discount (`price_base`), brand,
  stock flag, canonical URL and image;
- the price boxes `old-price-<id>` / `product-price-<id>` (`data-price-amount`), which
  win over the analytics prices because they are what the shopper sees;
- the nested JSON-LD `mpn`, which holds the EAN (kept only if its check digit is valid).

Discovery: the sitemaps `/sitemap/sitemap-1-{1,2,3}.xml` mix categories and products.
Product URLs are single-segment paths (`/masca-de-fata-guinot-…-8ml`); categories are
nested (`/ten/exfoliere/masti`), except the top-level ones (`/ten`), which slip through
the URL filter and are dropped by the parser (no `product_viewed` event).
"""

import json
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from beautycrawler.crawler.scraped import ScrapedOffer, normalize_gtin
from beautycrawler.crawler.spider import Spider, register

_HOST = "www.xpertbeauty.ro"
_WANTED_SITEMAP = re.compile(r"^/(?:sitemap\.xml|sitemap/[\w-]+\.xml)$")
_PRODUCT_PATH = re.compile(r"^/[^/.]+$")
_EVENTS_KEY = "Evx_DataReshape/js/events"


def _bani(value: object) -> int | None:
    """Machine-formatted amount ("59.2", 74, 59.2) in bani; None if not a number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _viewed_product(tree: HTMLParser) -> dict[str, Any] | None:
    """The product of the `product_viewed` analytics event, if the page has one."""
    for script in tree.css('script[type="text/x-magento-init"]'):
        text = script.text()
        if _EVENTS_KEY not in text:
            continue
        try:
            data = json.loads(text)
            events = data["*"][_EVENTS_KEY]["events"]
        except (ValueError, KeyError, TypeError):
            continue
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            info = event.get("event")
            name = info.get("name") if isinstance(info, dict) else None
            products = event.get("products")
            if name == "product_viewed" and isinstance(products, list) and products:
                product = products[0]
                if isinstance(product, dict):
                    return product
    return None


def _mpn(tree: HTMLParser) -> str | None:
    """`mpn`/`gtin13` of the JSON-LD `Product` nested in the page's `ItemPage`."""
    for script in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.text())
        except ValueError:
            continue
        entity = data.get("mainEntity") if isinstance(data, dict) else None
        if isinstance(entity, dict) and entity.get("@type") == "Product":
            return normalize_gtin(entity.get("gtin13")) or normalize_gtin(entity.get("mpn"))
    return None


def _price_box(tree: HTMLParser, element_id: str) -> int | None:
    node = tree.css_first(f'[id="{element_id}"]')
    return _bani(node.attributes.get("data-price-amount")) if node else None


@register
class XpertBeautySpider(Spider):
    slug = "xpertbeauty"
    name = "XpertBeauty"
    base_url = f"https://{_HOST}"
    sitemap_urls = tuple(f"https://{_HOST}/sitemap/sitemap-1-{n}.xml" for n in (1, 2, 3))

    def is_wanted_sitemap(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.netloc.lower() == _HOST and bool(_WANTED_SITEMAP.match(parts.path))

    def is_product_url(self, url: str) -> bool:
        parts = urlsplit(url)
        return (
            parts.netloc.lower() == _HOST
            and not parts.query
            and bool(_PRODUCT_PATH.match(parts.path))
        )

    def parse_product(self, html: str, url: str) -> list[ScrapedOffer]:
        tree = HTMLParser(html)
        product = _viewed_product(tree)
        if product is None:
            return []
        product_id = str(product.get("id") or "")
        price = _price_box(tree, f"product-price-{product_id}")
        if price is None:
            price = _bani(product.get("price"))
        title = str(product.get("name") or "").strip()
        if not title:
            h1 = tree.css_first("h1")
            title = h1.text(strip=True) if h1 else ""
        if price is None or not title:
            return []
        old_price = _price_box(tree, f"old-price-{product_id}")
        if old_price is None:
            old_price = _bani(product.get("price_base"))
        page_url = product.get("url")
        image = product.get("image")
        stock = product.get("stock_status")
        return [
            ScrapedOffer(
                retailer=self.slug,
                url=urljoin(url, page_url) if isinstance(page_url, str) and page_url else url,
                title=title,
                price_bani=price,
                old_price_bani=old_price,
                currency=str(product.get("currency") or "RON"),
                in_stock=stock is True or stock in (1, "1", "true", "in_stock"),
                brand=str(product.get("brand") or "").strip() or None,
                ean=_mpn(tree),
                image_url=urljoin(url, image) if isinstance(image, str) and image else None,
            )
        ]
