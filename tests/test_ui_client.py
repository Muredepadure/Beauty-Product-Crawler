"""P7.5: the UI's API client, contract-tested against the real FastAPI app."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from beautycrawler.config import get_settings
from beautycrawler.db.models import Brand, Product, Retailer
from beautycrawler.db.repository import OfferSnapshot, upsert_offer
from beautycrawler.ui_client import ApiClient, ApiError, NotFound, format_lei


@pytest.fixture
def api(client: TestClient) -> Iterator[ApiClient]:
    client.base_url = httpx.URL("http://testserver/api")
    yield ApiClient(http=client)


@pytest.fixture
def product_id(api_session: Session) -> int:
    s = api_session
    notino = Retailer(slug="notino", name="Notino", domain="notino.ro")
    s.add(notino)
    product = Product(
        brand=Brand(name="La Roche-Posay", normalized_name="la roche posay"),
        name="Effaclar Duo+",
        normalized_name="effaclar duo+",
        category="Îngrijirea tenului",
        size_value=Decimal(40),
        size_unit="ml",
    )
    s.add(product)
    s.flush()
    now = datetime.now(UTC)
    for hours_ago, price in ((48, 8_990), (2, 6_990)):
        snap = OfferSnapshot(
            url="https://notino.ro/duo", title="Effaclar", price_bani=price, in_stock=True
        )
        result = upsert_offer(s, notino, snap, now - timedelta(hours=hours_ago))
        result.offer.product = product
    s.commit()
    return product.id


def test_client_round_trips_every_endpoint(api: ApiClient, product_id: int) -> None:
    page = api.search_products("effaclar", brand="LRP", sort="price_asc")
    assert page.total == 1
    [summary] = page.items
    assert (summary.id, summary.lowest_price_bani, summary.size_value) == (
        product_id,
        6_990,
        Decimal(40),
    )

    detail = api.get_product(product_id)
    assert [o.retailer.slug for o in detail.offers] == ["notino"]
    assert detail.offers[0].is_cheapest

    history = api.get_history(product_id, days=30)
    assert [p.price_bani for p in history.series[0].points] == [8_990, 6_990]

    assert [r.slug for r in api.list_retailers()] == ["notino"]
    assert [b.name for b in api.list_brands("roche").items] == ["La Roche-Posay"]

    comparison = api.compare("La Roche-Posay")
    assert comparison.products[0].market_min_bani == 6_990

    drops = api.price_drops(min_pct=10)
    assert [(d.previous_price_bani, d.price_bani) for d in drops.items] == [(8_990, 6_990)]


def test_empty_params_are_not_sent(api: ApiClient, product_id: int) -> None:
    # "" would be a real filter value for the API; the client treats it as "no filter"
    assert api.search_products("", brand="", category=None).total == 1


def test_not_found(api: ApiClient) -> None:
    with pytest.raises(NotFound) as err:
        api.get_product(12345)
    assert err.value.status_code == 404
    with pytest.raises(NotFound):
        api.compare("No Such Brand")


def test_validation_error_is_an_api_error(api: ApiClient) -> None:
    with pytest.raises(ApiError) as err:
        api.search_products(page=0)
    assert err.value.status_code == 422


def test_unreachable_api() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("http://api.test/api/retailers").mock(side_effect=httpx.ConnectError("refused"))
        with ApiClient("http://api.test/api/") as api, pytest.raises(ApiError, match="unreachable"):
            api.list_retailers()


def test_server_error() -> None:
    with respx.mock() as router:
        router.get("http://api.test/api/retailers").mock(
            return_value=httpx.Response(500, text="boom")
        )
        with ApiClient("http://api.test/api") as api, pytest.raises(ApiError) as err:
            api.list_retailers()
    assert err.value.status_code == 500


def test_base_url_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEAUTYCRAWLER_API_BASE_URL", "http://configured.test/api")
    get_settings.cache_clear()
    try:
        with respx.mock() as router:
            route = router.get("http://configured.test/api/retailers").mock(
                return_value=httpx.Response(200, json=[])
            )
            with ApiClient() as api:
                assert api.list_retailers() == []
            assert route.called
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    ("bani", "text"),
    [
        (0, "0,00 lei"),
        (5, "0,05 lei"),
        (8_990, "89,90 lei"),
        (123_456_789, "1.234.567,89 lei"),
        (-1_050, "-10,50 lei"),
        (None, "—"),
    ],
)
def test_format_lei(bani: int | None, text: str) -> None:
    assert format_lei(bani) == text
