"""ProBeauty (probeauty.ro): professional hair tools and care.

Audit (2026-10-18): a Shopify store. robots.txt allows `/products/*`; `/sitemap.xml`
lists `sitemap_products_<n>.xml`. Complete `Product` JSON-LD (price, availability,
GTIN, brand, image). See `crawler/shopify.py` for the shared layout.
"""

from beautycrawler.crawler.shopify import ShopifySpider
from beautycrawler.crawler.spider import register


@register
class ProBeautySpider(ShopifySpider):
    slug = "probeauty"
    name = "ProBeauty"
    base_url = "https://probeauty.ro"
    hosts = frozenset({"probeauty.ro", "www.probeauty.ro"})
