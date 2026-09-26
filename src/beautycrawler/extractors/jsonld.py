"""Extract schema.org `Product` / `Offer` data from JSON-LD blocks.

Handles what Romanian shops actually emit: `@graph` containers, `@type` as a string or
list (with or without the schema.org prefix), `ProductGroup` + `hasVariant`, `offers`
as an object, a list or an `AggregateOffer`, brand as text or a `Brand` object,
GTIN under any of `gtin13`/`gtin`/`gtin8`/`gtin12`/`gtin14`/`ean`, prices as numbers or
strings with comma decimals, and sale prices via `priceSpecification` (`ListPrice` /
`StrikethroughPrice`).

JSON-LD script blocks are parsed one by one (not with `extruct`, which drops every block
on a page when a single one is malformed), so a broken block elsewhere on the page doesn't
hide the product.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from beautycrawler.crawler.scraped import ScrapedOffer, normalize_gtin
from beautycrawler.extractors.price import parse_machine_price

JsonObj = dict[str, Any]

_GTIN_KEYS = ("gtin13", "gtin", "gtin8", "gtin12", "gtin14", "ean", "isbn")
# schema.org ItemAvailability values that mean "can be bought online now".
_IN_STOCK = {"instock", "limitedavailability", "onlineonly"}
_OUT_OF_STOCK = {
    "outofstock",
    "soldout",
    "discontinued",
    "preorder",
    "presale",
    "backorder",
    "instoreonly",
}
_OLD_PRICE_TYPES = {"listprice", "strikethroughprice", "msrp", "srp"}


@dataclass(frozen=True, slots=True)
class JsonLdOffer:
    price_bani: int
    currency: str
    in_stock: bool | None  # None when availability isn't stated
    old_price_bani: int | None = None
    url: str | None = None
    sku: str | None = None
    gtin: str | None = None
    seller: str | None = None


@dataclass(frozen=True, slots=True)
class JsonLdProduct:
    name: str
    brand: str | None = None
    gtin: str | None = None
    sku: str | None = None
    url: str | None = None
    image: str | None = None
    offers: list[JsonLdOffer] = field(default_factory=list)


# --------------------------------------------------------------------------- parsing


def iter_jsonld_objects(html: str) -> Iterator[JsonObj]:
    """Every JSON object in the page's JSON-LD blocks, with `@graph`s and lists flattened."""
    tree = HTMLParser(html)
    for node in tree.css('script[type="application/ld+json"]'):
        text = (node.text(deep=True) or "").strip()
        if not text:
            continue
        try:
            data = json.loads(text, strict=False)  # tolerate raw newlines inside strings
        except json.JSONDecodeError:
            continue
        yield from _flatten(data)


def _flatten(data: Any) -> Iterator[JsonObj]:
    if isinstance(data, list):
        for item in data:
            yield from _flatten(item)
    elif isinstance(data, dict):
        if "@graph" in data:
            yield from _flatten(data["@graph"])
        else:
            yield data


def _types(obj: JsonObj) -> set[str]:
    raw = obj.get("@type", [])
    values = raw if isinstance(raw, list) else [raw]
    return {str(v).rsplit("/", 1)[-1].rsplit(":", 1)[-1].lower() for v in values}


def _text(value: Any) -> str | None:
    """A plain string from text / {name|@value|url} objects / lists (first usable item)."""
    if isinstance(value, list):
        for item in value:
            text = _text(item)
            if text:
                return text
        return None
    if isinstance(value, dict):
        for key in ("name", "@value", "url", "contentUrl"):
            if key in value:
                return _text(value[key])
        return None
    if isinstance(value, str | int | float) and not isinstance(value, bool):
        text = str(value).strip()
        return text or None
    return None


def _enum(value: Any) -> str | None:
    text = _text(value)
    return text.rsplit("/", 1)[-1].lower() if text else None


def _gtin(obj: JsonObj) -> str | None:
    for key in _GTIN_KEYS:
        gtin = normalize_gtin(_text(obj.get(key)))
        if gtin:
            return gtin
    return None


def _availability(obj: JsonObj) -> bool | None:
    value = _enum(obj.get("availability"))
    if value in _IN_STOCK:
        return True
    if value in _OUT_OF_STOCK:
        return False
    return None


def _price_specs(obj: JsonObj) -> list[JsonObj]:
    spec = obj.get("priceSpecification")
    specs = spec if isinstance(spec, list) else [spec]
    return [s for s in specs if isinstance(s, dict)]


def _parse_offer(obj: JsonObj, inherited_currency: str | None = None) -> JsonLdOffer | None:
    specs = _price_specs(obj)
    current_specs = [s for s in specs if _enum(s.get("priceType")) not in _OLD_PRICE_TYPES]
    old_specs = [s for s in specs if _enum(s.get("priceType")) in _OLD_PRICE_TYPES]

    price = parse_machine_price(obj.get("price"))
    if price is None:
        price = parse_machine_price(obj.get("lowPrice"))
    if price is None and current_specs:
        price = parse_machine_price(current_specs[0].get("price"))
    if price is None:
        return None

    old_price = None
    if old_specs:
        old_price = parse_machine_price(old_specs[0].get("price"))
    currency = (
        _text(obj.get("priceCurrency"))
        or next((_text(s.get("priceCurrency")) for s in specs if s.get("priceCurrency")), None)
        or inherited_currency
        or "RON"
    )
    return JsonLdOffer(
        price_bani=price,
        old_price_bani=old_price if old_price is not None and old_price > price else None,
        currency=currency.upper(),
        in_stock=_availability(obj),
        url=_text(obj.get("url")),
        sku=_text(obj.get("sku")),
        gtin=_gtin(obj),
        seller=_text(obj.get("seller")),
    )


def _parse_offers(value: Any) -> list[JsonLdOffer]:
    items = value if isinstance(value, list) else [value]
    offers: list[JsonLdOffer] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        nested = item.get("offers")
        if "aggregateoffer" in _types(item) and nested:
            currency = _text(item.get("priceCurrency"))
            for sub in nested if isinstance(nested, list) else [nested]:
                if isinstance(sub, dict) and (offer := _parse_offer(sub, currency)):
                    offers.append(offer)
            continue
        if offer := _parse_offer(item):
            offers.append(offer)
    return offers


def _parse_product(obj: JsonObj, parent: JsonObj | None = None) -> JsonLdProduct | None:
    parent = parent or {}
    name = _text(obj.get("name")) or _text(parent.get("name"))
    if not name:
        return None
    return JsonLdProduct(
        name=name,
        brand=_text(obj.get("brand")) or _text(parent.get("brand")),
        gtin=_gtin(obj),
        sku=_text(obj.get("sku")),
        url=_text(obj.get("url")) or _text(parent.get("url")),
        image=_text(obj.get("image")) or _text(parent.get("image")),
        offers=_parse_offers(obj.get("offers")),
    )


def extract_products(html: str) -> list[JsonLdProduct]:
    """All schema.org products on the page; a `ProductGroup` yields one per variant."""
    products: list[JsonLdProduct] = []
    for obj in iter_jsonld_objects(html):
        types = _types(obj)
        if "productgroup" in types:
            variants = obj.get("hasVariant") or []
            for variant in variants if isinstance(variants, list) else [variants]:
                if isinstance(variant, dict) and (p := _parse_product(variant, obj)):
                    products.append(p)
        elif "product" in types and (p := _parse_product(obj)):
            products.append(p)
    return products


# ------------------------------------------------------------------ to spider output


def to_scraped_offers(
    products: list[JsonLdProduct], *, retailer: str, page_url: str
) -> list[ScrapedOffer]:
    """One `ScrapedOffer` per (product, offer), with URLs resolved against `page_url`.

    Variants that share a URL get `#sku=<sku>` appended so each is stored separately.

    Missing availability is taken as in stock: shops list availability when a product
    can't be bought, and a price without it is normally purchasable. Offers in a currency
    other than RON are skipped.
    """
    scraped: list[ScrapedOffer] = []
    seen_urls: set[str] = set()
    for product in products:
        for offer in product.offers:
            if offer.currency != "RON":
                continue
            url = urljoin(page_url, offer.url or product.url or page_url)
            if url in seen_urls:
                # Variants sharing one page URL: the DB keys offers on (retailer, url), so
                # tell them apart by SKU in the fragment; without a SKU keep the first only.
                sku = offer.sku or product.sku
                if not sku:
                    continue
                url = f"{url.split('#', 1)[0]}#sku={sku}"
                if url in seen_urls:
                    continue
            seen_urls.add(url)
            image = urljoin(page_url, product.image) if product.image else None
            scraped.append(
                ScrapedOffer(
                    retailer=retailer,
                    url=url,
                    title=product.name,
                    price_bani=offer.price_bani,
                    old_price_bani=offer.old_price_bani,
                    currency=offer.currency,
                    in_stock=offer.in_stock if offer.in_stock is not None else True,
                    brand=product.brand,
                    ean=offer.gtin or product.gtin,
                    image_url=image,
                    seller_name=offer.seller,
                )
            )
    return scraped
