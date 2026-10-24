"""Profihairshop (www.profihairshop.ro): professional hair and body care.

Audit (2026-10-18): robots.txt allows everything but asks for `Crawl-delay: 10`, which
the shared `PoliteFetcher` honours (one request per 10 s: a full crawl of ~1 300
products takes about 3.6 hours). `profihairshop.ro` redirects to `www.`; the fetcher
follows the redirect for robots.txt and checks robots.txt on every hop.

Product pages carry a complete schema.org `Product` JSON-LD block (name, price,
availability, GTIN, brand, image), so the generic JSON-LD parser is enough.

Discovery: the sitemap index `/sitemap-index.xml` lists `products-sitemap.xml` next to
page, category and brand sitemaps, which are skipped. Product URLs nest under their
category path (`/par/vopsele-oxidanti/<slug>`, `/seturi-cadou/<slug>`), so they look
like category URLs: only URLs from the products sitemap are treated as products.
"""

from urllib.parse import urlsplit

from beautycrawler.crawler.spider import JsonLdSpider, register

_HOSTS = frozenset({"www.profihairshop.ro", "profihairshop.ro"})
_WANTED_SITEMAPS = frozenset({"/sitemap-index.xml", "/products-sitemap.xml"})


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
