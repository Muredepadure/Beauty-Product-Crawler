from pathlib import Path

import pytest

from beautycrawler.extractors.jsonld import (
    JsonLdOffer,
    JsonLdProduct,
    extract_products,
    iter_jsonld_objects,
    to_scraped_offers,
)

FIXTURES = Path(__file__).parent / "fixtures" / "jsonld"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_single_offer() -> None:
    [product] = extract_products(load("single_offer.html"))
    assert product.name == "La Roche-Posay Effaclar Duo+ Cremă corectoare 40 ml"
    assert product.brand == "La Roche-Posay"
    assert product.gtin == "3337875598996"
    assert product.image == "/images/effaclar-40.jpg"  # first of a list
    [offer] = product.offers
    assert offer == JsonLdOffer(
        price_bani=8999,
        currency="RON",
        in_stock=True,
        url="https://shop.example.ro/la-roche-posay/effaclar-duo-plus-40ml",
    )


def test_product_group_variants() -> None:
    small, large = extract_products(load("variants.html"))
    assert (small.name, large.name) == (
        "Bioderma Sensibio H2O 250 ml",
        "Bioderma Sensibio H2O 500 ml",
    )
    # brand/url/image inherited from the ProductGroup
    assert small.brand == large.brand == "Bioderma"
    assert small.url == "https://shop.example.ro/bioderma/sensibio-h2o"
    assert small.image == "https://cdn.example.ro/sensibio.jpg"  # ImageObject
    assert (small.gtin, large.gtin) == ("3401345935571", "3401396991564")
    assert [(o.price_bani, o.in_stock) for o in small.offers + large.offers] == [
        (5490, True),
        (7990, False),  # bare "OutOfStock" without the schema.org prefix
    ]


def test_missing_gtin_comma_price_graph_and_broken_block() -> None:
    [product] = extract_products(load("missing_gtin_comma_price.html"))
    assert product.name == "CeraVe Hydrating Cleanser 236 ml"
    assert product.brand == "CeraVe"  # list of Brand objects
    assert product.gtin is None
    [offer] = product.offers
    assert offer.price_bani == 123450  # "1.234,50"
    assert offer.in_stock is True  # LimitedAvailability


def test_sale_price_specification_and_aggregate_offer() -> None:
    niacinamide, vichy = extract_products(load("sale_and_aggregate.html"))
    [sale] = niacinamide.offers
    assert (sale.price_bani, sale.old_price_bani) == (3990, 4990)
    assert niacinamide.gtin == "769915190311"  # "gtin" key, UPC-A
    assert [(o.price_bani, o.seller) for o in vichy.offers] == [
        (8900, "Seller A"),
        (11900, "Seller B"),
    ]
    assert all(o.currency == "RON" for o in vichy.offers)  # inherited from AggregateOffer


def test_aggregate_offer_without_nested_offers_uses_low_price() -> None:
    html = """<script type="application/ld+json">
    {"@type": "Product", "name": "X", "offers": {"@type": "AggregateOffer",
     "lowPrice": "10,50", "highPrice": "20", "priceCurrency": "RON"}}</script>"""
    [product] = extract_products(html)
    assert [o.price_bani for o in product.offers] == [1050]


@pytest.mark.parametrize(
    ("availability", "expected"),
    [
        ("https://schema.org/InStock", True),
        ("http://schema.org/OnlineOnly", True),
        ("https://schema.org/OutOfStock", False),
        ("https://schema.org/SoldOut", False),
        ("https://schema.org/PreOrder", False),
        ("https://schema.org/Discontinued", False),
        ("something-else", None),
        (None, None),
    ],
)
def test_availability(availability: str | None, expected: bool | None) -> None:
    avail = f'"availability": "{availability}",' if availability else ""
    html = f"""<script type="application/ld+json">
    {{"@type": "Product", "name": "X",
      "offers": {{{avail} "price": "10", "priceCurrency": "RON"}}}}</script>"""
    [product] = extract_products(html)
    assert product.offers[0].in_stock is expected


def test_invalid_gtin_and_bad_prices_are_dropped() -> None:
    html = """<script type="application/ld+json">
    {"@type": "Product", "name": "X", "gtin13": "1234567890123",
     "offers": [{"price": "la cerere"}, {"price": "-3"}, {"price": 12}]}</script>"""
    [product] = extract_products(html)
    assert product.gtin is None
    assert [o.price_bani for o in product.offers] == [1200]


def test_old_price_not_above_price_ignored() -> None:
    html = """<script type="application/ld+json">
    {"@type": "Product", "name": "X", "offers": {"price": "50", "priceSpecification":
      {"price": "40", "priceType": "https://schema.org/StrikethroughPrice"}}}</script>"""
    [product] = extract_products(html)
    assert product.offers[0].old_price_bani is None


def test_no_jsonld_or_no_product() -> None:
    assert extract_products("<html><body>nimic</body></html>") == []
    assert extract_products('<script type="application/ld+json">{"@type":"Thing"}</script>') == []
    assert extract_products('<script type="application/ld+json">{"@type":"Product"}</script>') == []
    assert extract_products('<script type="application/ld+json"> </script>') == []


def test_iter_jsonld_objects_flattens_graph_and_lists() -> None:
    types = [o.get("@type") for o in iter_jsonld_objects(load("missing_gtin_comma_price.html"))]
    assert types == ["WebSite", "BreadcrumbList", ["Product", "Thing"]]


# ------------------------------------------------------------------ to_scraped_offers


def test_to_scraped_offers_single() -> None:
    products = extract_products(load("single_offer.html"))
    page = "https://shop.example.ro/la-roche-posay/effaclar-duo-plus-40ml?utm=x"
    [offer] = to_scraped_offers(products, retailer="example", page_url=page)
    assert offer.retailer == "example"
    assert offer.url == "https://shop.example.ro/la-roche-posay/effaclar-duo-plus-40ml"
    assert offer.image_url == "https://shop.example.ro/images/effaclar-40.jpg"  # resolved
    assert (offer.price_bani, offer.in_stock, offer.ean) == (8999, True, "3337875598996")
    assert offer.brand == "La Roche-Posay"


def test_to_scraped_offers_relative_offer_url() -> None:
    products = extract_products(load("missing_gtin_comma_price.html"))
    [offer] = to_scraped_offers(products, retailer="x", page_url="https://shop.example.ro/p/1")
    assert offer.url == "https://shop.example.ro/cerave/hydrating-cleanser-236ml"
    assert offer.ean is None


def test_to_scraped_offers_variants_sharing_url_use_sku_fragment() -> None:
    products = extract_products(load("variants.html"))
    offers = to_scraped_offers(products, retailer="x", page_url="https://shop.example.ro/b")
    assert [(o.url, o.price_bani, o.in_stock) for o in offers] == [
        ("https://shop.example.ro/bioderma/sensibio-h2o", 5490, True),
        ("https://shop.example.ro/bioderma/sensibio-h2o#sku=BIO-H2O-500", 7990, False),
    ]
    assert [o.ean for o in offers] == ["3401345935571", "3401396991564"]


def test_to_scraped_offers_marketplace_sellers() -> None:
    products = extract_products(load("sale_and_aggregate.html"))
    offers = to_scraped_offers(products, retailer="m", page_url="https://market.example.ro/p")
    assert [(o.price_bani, o.old_price_bani, o.seller_name) for o in offers] == [
        (3990, 4990, None),
        (8900, None, "Seller A"),
        (11900, None, "Seller B"),
    ]


def test_to_scraped_offers_skips_foreign_currency_and_unknown_stock_is_in_stock() -> None:
    products = [
        JsonLdProduct(
            name="X",
            offers=[
                JsonLdOffer(price_bani=100, currency="EUR", in_stock=True, url="https://a.ro/e"),
                JsonLdOffer(price_bani=500, currency="RON", in_stock=None, url="https://a.ro/r"),
            ],
        )
    ]
    [offer] = to_scraped_offers(products, retailer="a", page_url="https://a.ro/")
    assert (offer.url, offer.in_stock) == ("https://a.ro/r", True)


def test_duplicate_url_without_sku_keeps_first() -> None:
    products = [
        JsonLdProduct(
            name="A", offers=[JsonLdOffer(price_bani=100, currency="RON", in_stock=True)]
        ),
        JsonLdProduct(
            name="B", offers=[JsonLdOffer(price_bani=200, currency="RON", in_stock=True)]
        ),
    ]
    offers = to_scraped_offers(products, retailer="a", page_url="https://a.ro/p")
    assert [(o.title, o.url) for o in offers] == [("A", "https://a.ro/p")]
