"""Beauty Lounge (beauty-lounge.ro): professional hair and skin care.

Audit (2026-10-18): a Shopify store laid out like ProBeauty (7 product sitemaps).
The JSON-LD carries sale prices (old price) but can cut the product name short, which
the shared Shopify base fixes from the `<h1>` (see `crawler/shopify.py`).
"""

from beautycrawler.crawler.shopify import ShopifySpider
from beautycrawler.crawler.spider import register


@register
class BeautyLoungeSpider(ShopifySpider):
    slug = "beautylounge"
    name = "Beauty Lounge"
    base_url = "https://beauty-lounge.ro"
    hosts = frozenset({"beauty-lounge.ro", "www.beauty-lounge.ro"})
