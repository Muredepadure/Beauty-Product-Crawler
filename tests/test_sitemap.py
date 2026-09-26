import gzip

from beautycrawler.crawler.sitemap import parse_sitemap

URLSET = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
  <url><loc> https://shop.example.ro/p/1 </loc><lastmod>2026-09-01</lastmod>
       <image:image><image:loc>https://cdn.example.ro/1.jpg</image:loc></image:image></url>
  <url><loc>https://shop.example.ro/p/2</loc></url>
  <url><loc></loc></url>
</urlset>"""

INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://shop.example.ro/sitemap-products-1.xml</loc></sitemap>
  <sitemap><loc>https://shop.example.ro/sitemap-products-2.xml.gz</loc></sitemap>
</sitemapindex>"""


def test_urlset() -> None:
    sm = parse_sitemap(URLSET)
    # image:loc inside <url> is not a page URL; empty <loc> skipped; whitespace stripped
    assert sm.urls == ["https://shop.example.ro/p/1", "https://shop.example.ro/p/2"]
    assert sm.sitemaps == []


def test_index() -> None:
    sm = parse_sitemap(INDEX)
    assert sm.sitemaps == [
        "https://shop.example.ro/sitemap-products-1.xml",
        "https://shop.example.ro/sitemap-products-2.xml.gz",
    ]
    assert sm.urls == []


def test_gzip() -> None:
    assert parse_sitemap(gzip.compress(URLSET)).urls[0] == "https://shop.example.ro/p/1"


def test_without_namespace() -> None:
    assert parse_sitemap(b"<urlset><url><loc>https://a.ro/x</loc></url></urlset>").urls == [
        "https://a.ro/x"
    ]


def test_garbage_is_empty() -> None:
    for content in (b"", b"   ", b"<html><body>not a sitemap</body></html>", b"\x1f\x8bnot-gzip"):
        sm = parse_sitemap(content)
        assert sm.urls == [] and sm.sitemaps == []


def test_entities_are_not_expanded() -> None:
    xxe = b"""<?xml version="1.0"?>
<!DOCTYPE urlset [<!ENTITY secret SYSTEM "file:///etc/passwd">]>
<urlset><url><loc>https://a.ro/&secret;</loc></url></urlset>"""
    urls = parse_sitemap(xxe).urls
    assert all("root:" not in u for u in urls)
