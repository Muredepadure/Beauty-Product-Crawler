"""Phase 7: the Streamlit UI, run headlessly with `AppTest`.

The UI's HTTP calls are routed (by respx) into the FastAPI test app backed by an
in-memory database, so these are end-to-end tests without any network.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from streamlit.testing.v1 import AppTest

from beautycrawler.config import get_settings
from beautycrawler.db.models import Brand, Product, Retailer
from beautycrawler.db.repository import OfferSnapshot, upsert_offer

APP = str(Path(__file__).resolve().parents[1] / "ui" / "App.py")
API_HOST = "ui-api.test"


@pytest.fixture
def ui_api(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[respx.MockRouter]:
    """Point the UI at a fake host and forward its requests to the test app."""
    monkeypatch.setenv("BEAUTYCRAWLER_API_BASE_URL", f"http://{API_HOST}/api")
    get_settings.cache_clear()

    def forward(request: httpx.Request) -> httpx.Response:
        r = client.request(request.method, request.url.raw_path.decode())
        return httpx.Response(r.status_code, content=r.content, headers=r.headers)

    with respx.mock(assert_all_called=False) as router:
        router.route(host=API_HOST).mock(side_effect=forward)
        yield router
    get_settings.cache_clear()


def run_app(query: dict[str, str] | None = None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.query_params.update(query or {})
    return at.run()


def _observe(
    s: Session, retailer: Retailer, product: Product, url: str, steps: list[tuple[int, int, bool]]
) -> None:
    now = datetime.now(UTC)
    for hours_ago, price, in_stock in steps:
        snap = OfferSnapshot(url=url, title=product.name, price_bani=price, in_stock=in_stock)
        upsert_offer(s, retailer, snap, now - timedelta(hours=hours_ago)).offer.product = product


@pytest.fixture
def shop(api_session: Session) -> dict[str, int]:
    s = api_session
    notino = Retailer(slug="notino", name="Notino", domain="notino.ro")
    emag = Retailer(slug="emag", name="eMAG", domain="emag.ro")
    lrp = Brand(name="La Roche-Posay", normalized_name="la roche posay")
    cerave = Brand(name="CeraVe", normalized_name="cerave")
    s.add_all([notino, emag])

    def product(brand: Brand, name: str, category: str) -> Product:
        p = Product(
            brand=brand,
            name=name,
            normalized_name=name.lower(),
            category=category,
            size_value=Decimal(40),
            size_unit="ml",
        )
        s.add(p)
        s.flush()
        return p

    duo = product(lrp, "Effaclar Duo+", "Îngrijirea tenului")
    cica = product(lrp, "Cicaplast Baume B5+", "Îngrijirea tenului")
    cleanser = product(cerave, "Hydrating Cleanser", "Curățare")
    _observe(s, notino, duo, "https://notino.ro/duo", [(72, 8_990, True), (5, 7_990, True)])
    _observe(s, emag, duo, "https://emag.ro/duo", [(48, 7_450, True)])
    _observe(s, notino, cica, "https://notino.ro/cica", [(48, 5_500, True)])
    _observe(s, emag, cica, "https://emag.ro/cica", [(48, 6_500, True)])
    _observe(s, emag, cleanser, "https://emag.ro/cleanser", [(48, 4_000, False)])
    s.commit()
    return {"duo": duo.id, "cica": cica.id, "cleanser": cleanser.id}


def markdown(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


# --- P7.1: search page -------------------------------------------------------------


def test_search_lists_products_as_cards(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app()
    assert not at.exception
    assert at.title[0].value == "🔎 Caută produse"
    assert at.subheader[0].value == "3 produse"
    text = markdown(at)
    assert "**Effaclar Duo+**" in text
    assert "de la 74,50 lei · 2 magazine" in text  # emag's 74,50 beats notino's 79,90
    assert "Stoc epuizat · 1 magazin" in text
    assert "La Roche-Posay · 40 ml" in [c.value for c in at.caption]
    assert len([b for b in at.button if b.label == "Vezi prețurile"]) == 3


def test_search_query_filters_cards(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app()
    at.text_input(key="q").input("CICAPLAST Bâume").run()  # case/diacritics ignored
    assert at.subheader[0].value == "1 produs"
    assert "**Cicaplast Baume B5+**" in markdown(at)
    at.text_input(key="q").input("nu exista").run()
    assert "Niciun produs găsit" in at.info[0].value


def test_search_sort_by_price(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app()
    at.selectbox(key="sort").select("price_asc").run()
    names = [m.value for m in at.markdown if m.value.startswith("**")]
    assert names == ["**Cicaplast Baume B5+**", "**Effaclar Duo+**", "**Hydrating Cleanser**"]


def test_search_shows_api_errors(ui_api: respx.MockRouter) -> None:
    ui_api.routes.clear()
    ui_api.route(host=API_HOST).mock(side_effect=httpx.ConnectError("refused"))
    at = run_app()
    assert not at.exception
    assert "Nu am putut încărca produsele" in at.error[0].value


def test_card_button_opens_product_page(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app()
    at.button(key=f"open-{shop['duo']}").click().run()
    assert at.query_params["product"] == [str(shop["duo"])]
    assert at.title[0].value == "Effaclar Duo+"
    at.button[0].click().run()  # back
    assert "product" not in at.query_params
    assert at.title[0].value == "🔎 Caută produse"


@pytest.mark.parametrize("value", ["999", "abc"])
def test_bad_product_ids(ui_api: respx.MockRouter, shop: dict[str, int], value: str) -> None:
    at = run_app({"product": value})
    assert not at.exception
    if value.isdigit():
        assert "Produsul nu există" in at.error[0].value
    else:
        assert at.title[0].value == "🔎 Caută produse"
