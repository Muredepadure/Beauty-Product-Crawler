"""Parse XML sitemaps and sitemap indexes (optionally gzip-compressed)."""

import gzip
import io
from dataclasses import dataclass, field

from lxml import etree

MAX_SITEMAP_BYTES = 50 * 1024 * 1024  # sitemaps.org limit (uncompressed)


@dataclass(frozen=True, slots=True)
class Sitemap:
    urls: list[str] = field(default_factory=list)  # <urlset><url><loc>
    sitemaps: list[str] = field(default_factory=list)  # <sitemapindex><sitemap><loc>


def _parser() -> etree.XMLParser:
    # No entity expansion, no network, no huge trees: sitemap XML is untrusted input.
    return etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, recover=True)


def parse_sitemap(content: bytes) -> Sitemap:
    """Parse sitemap bytes (plain or gzip). Malformed input yields an empty Sitemap."""
    if content[:2] == b"\x1f\x8b":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(content)) as gz:
                content = gz.read(MAX_SITEMAP_BYTES + 1)
        except (OSError, EOFError):
            return Sitemap()
    if not content.strip() or len(content) > MAX_SITEMAP_BYTES:
        return Sitemap()
    try:
        root = etree.fromstring(content, parser=_parser())
    except etree.XMLSyntaxError:
        return Sitemap()
    if root is None:
        return Sitemap()

    def locs(parent_tag: str) -> list[str]:
        found = []
        for el in root.iter():
            if not isinstance(el.tag, str) or etree.QName(el).localname != parent_tag:
                continue
            for child in el:
                if isinstance(child.tag, str) and etree.QName(child).localname == "loc":
                    text = (child.text or "").strip()
                    if text:
                        found.append(text)
        return found

    kind = etree.QName(root).localname if isinstance(root.tag, str) else ""
    if kind == "sitemapindex":
        return Sitemap(sitemaps=locs("sitemap"))
    if kind == "urlset":
        return Sitemap(urls=locs("url"))
    return Sitemap()
