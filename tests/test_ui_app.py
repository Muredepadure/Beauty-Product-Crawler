"""Phase 7: the Streamlit UI, run headlessly with `AppTest`.

The UI's HTTP calls are routed (by respx) into the FastAPI test app backed by an
in-memory database, so these are end-to-end tests without any network.
"""

import html
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx
import streamlit as st
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from streamlit.testing.v1 import AppTest

from beautycrawler.config import get_settings
from beautycrawler.db.models import Brand, Product, Retailer
from beautycrawler.db.repository import OfferSnapshot, upsert_offer
from beautycrawler.ui_style import TAGLINE

APP = str(Path(__file__).resolve().parents[1] / "ui" / "App.py")
API_HOST = "ui-api.test"


@pytest.fixture
def ui_api(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[respx.MockRouter]:
    """Point the UI at a fake host and forward its requests to the test app."""
    monkeypatch.setenv("BEAUTYCRAWLER_API_BASE_URL", f"http://{API_HOST}/api")
    get_settings.cache_clear()
    st.cache_data.clear()  # e.g. the brand list, which differs per test database

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


def card_markup(at: AppTest) -> list[str]:
    return [m.value for m in at.markdown if m.value.startswith('<div class="bc-card">')]


def card_names(at: AppTest) -> list[str]:
    names = (re.search(r'class="bc-card-name"[^>]*>(.*?)</div>', c) for c in card_markup(at))
    return [html.unescape(m.group(1)) for m in names if m]


# --- P7.1: search page -------------------------------------------------------------


def test_search_lists_products_as_cards(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app()
    assert not at.exception
    assert at.title[0].value == "🔎 Caută produse"
    assert at.subheader[0].value == "3 produse"
    cards = dict(zip(card_names(at), card_markup(at), strict=True))
    assert list(cards) == ["Cicaplast Baume B5+", "Effaclar Duo+", "Hydrating Cleanser"]
    duo = cards["Effaclar Duo+"]
    assert '<div class="bc-card-brand">La Roche-Posay</div>' in duo
    assert '<div class="bc-card-size">40 ml</div>' in duo
    # emag's 74,50 beats notino's 79,90
    assert '<span class="bc-from">de la</span> 74,50 lei' in duo
    assert '<div class="bc-card-stores">la 2 magazine</div>' in duo
    assert "bc-badge" not in duo
    cleanser = cards["Hydrating Cleanser"]
    assert '<span class="bc-badge bc-badge-out">Stoc epuizat</span>' in cleanser
    assert '<div class="bc-card-stores">la 1 magazin</div>' in cleanser
    assert all("bc-card-placeholder" in c for c in cards.values())  # no images
    assert len([b for b in at.button if b.label == "Vezi prețurile"]) == 3


def test_header_on_every_page(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    for at in (run_app(), run_app({"product": str(shop["duo"])})):
        assert not at.exception
        assert at.markdown[0].value == ":primary[**💄 BeautyCrawler**]"
        assert at.caption[0].value == TAGLINE
    at = run_app()
    at.radio(key="nav").set_value("🏷️ Comparație prețuri").run()
    assert at.markdown[0].value == ":primary[**💄 BeautyCrawler**]"


def test_search_query_filters_cards(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app()
    at.text_input(key="q").input("CICAPLAST Bâume").run()  # case/diacritics ignored
    assert at.subheader[0].value == "1 produs"
    assert card_names(at) == ["Cicaplast Baume B5+"]
    at.text_input(key="q").input("nu exista").run()
    assert "Niciun produs găsit" in markdown(at)
    assert "Verifică ortografia" in markdown(at)
    assert not at.subheader  # no "0 produse" above the empty state
    assert [b.key for b in at.button if b.label == "Resetează filtrele"] == ["reset_filters"]


def test_search_empty_database(ui_api: respx.MockRouter) -> None:
    at = run_app()
    assert not at.exception
    assert "Încă nu există produse în catalog." in markdown(at)


def test_reset_filters(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app()
    assert at.button(key="reset_filters").disabled  # nothing to reset
    at.selectbox(key="brand").select("CeraVe").run()
    at.checkbox(key="in_stock").check().run()  # CeraVe's only product is out of stock
    assert "Încearcă mai puține filtre" in markdown(at)
    assert not at.button(key="reset_filters").disabled
    at.button(key="reset_filters_empty").click().run()
    assert at.selectbox(key="brand").value == "Toate brandurile"
    assert at.checkbox(key="in_stock").value is False
    assert len(card_names(at)) == 3
    assert at.button(key="reset_filters").disabled


def test_search_sort_by_price(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app()
    at.selectbox(key="sort").select("price_asc").run()
    assert card_names(at) == ["Cicaplast Baume B5+", "Effaclar Duo+", "Hydrating Cleanser"]


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


# --- P7.2: product page ------------------------------------------------------------


def _chart_specs(at: AppTest) -> list[str]:
    return [e.proto.spec for e in at.main if getattr(e, "type", "") == "vega_lite_chart"]


def offer_table(at: AppTest) -> str:
    [table] = [m.value for m in at.markdown if m.value.startswith('<div class="bc-offers">')]
    return table


def test_product_page_price_table(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app({"product": str(shop["duo"])})
    assert not at.exception
    assert at.title[0].value == "Effaclar Duo+"
    header = markdown(at)
    assert '<div class="bc-card-brand bc-detail-brand">La Roche-Posay</div>' in header
    assert '<div class="bc-detail-meta">40 ml</div>' in header
    assert '<span class="bc-from">de la</span> 74,50 lei' in header
    assert '<div class="bc-card-stores">la 2 magazine</div>' in header
    table = offer_table(at)
    rows = re.findall(r"<tr[ >].*?</tr>", table.split("<tbody>")[1])
    assert [re.findall(r'bc-col-store">([^<]*)', r) for r in rows] == [["eMAG"], ["Notino"]]
    assert rows[0].startswith('<tr class="bc-cheapest">')  # emag's 74,50 beats 79,90
    assert "Cel mai mic preț" in rows[0] and "Cel mai mic preț" not in rows[1]
    assert "74,50 lei" in rows[0] and "79,90 lei" in rows[1]
    assert all("În stoc" in r for r in rows)
    assert 'href="https://emag.ro/duo"' in rows[0] and 'href="https://notino.ro/duo"' in rows[1]
    assert table.count("Vezi în magazin") == 2


def test_product_page_history_chart(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app({"product": str(shop["duo"])})
    [spec] = _chart_specs(at)
    assert '"step-after"' in spec
    assert at.selectbox(key="period").value == "90 de zile"
    at.selectbox(key="period").select("Tot istoricul").run()
    assert not at.exception
    assert len(_chart_specs(at)) == 1


def test_product_page_out_of_stock_only(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app({"product": str(shop["cleanser"])})
    assert '<div class="bc-card-price bc-muted">Indisponibil</div>' in markdown(at)
    assert "Stoc epuizat" in markdown(at)  # the badge on the image
    table = offer_table(at)
    assert "bc-out-of-stock" in table and "bc-cheapest" not in table


def test_product_page_without_offers(ui_api: respx.MockRouter, api_session: Session) -> None:
    product = Product(name="Nou pe piață", normalized_name="nou pe piata")
    api_session.add(product)
    api_session.commit()
    at = run_app({"product": str(product.id)})
    assert not at.exception
    infos = [i.value for i in at.info]
    assert "Niciun magazin nu are încă oferte pentru acest produs." in infos
    assert "Nu există încă istoric de prețuri." in infos


# --- P7.3: filters ---------------------------------------------------------------------


def test_brand_filter(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app()
    assert at.selectbox(key="brand").options == ["Toate brandurile", "CeraVe", "La Roche-Posay"]
    at.selectbox(key="brand").select("CeraVe").run()
    assert card_names(at) == ["Hydrating Cleanser"]


def test_category_filter_ignores_diacritics(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app()
    at.text_input(key="category").input("ingrijirea tenului").run()
    assert card_names(at) == ["Cicaplast Baume B5+", "Effaclar Duo+"]


def test_price_range_filter(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app()
    at.number_input(key="min_lei").set_value(60.0).run()
    assert card_names(at) == ["Effaclar Duo+"]  # 74,50 lei; Cicaplast is 55 lei
    at.number_input(key="min_lei").set_value(0.0)
    at.number_input(key="max_lei").set_value(60.0).run()
    assert card_names(at) == ["Cicaplast Baume B5+"]


def test_in_stock_only(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = run_app()
    assert "Hydrating Cleanser" in card_names(at)
    at.checkbox(key="in_stock").check().run()
    assert card_names(at) == ["Cicaplast Baume B5+", "Effaclar Duo+"]


# --- P7.4: competitor view -------------------------------------------------------------


def open_competitors() -> AppTest:
    at = run_app()
    at.radio(key="nav").set_value("🏷️ Comparație prețuri").run()
    assert not at.exception
    return at


def test_competitor_view(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = open_competitors()
    assert at.title[0].value == "🏷️ Comparație prețuri"
    at.selectbox(key="cmp_brand").select("La Roche-Posay").run()
    matrix, detail = (d.value for d in at.dataframe)

    # duo: emag 74,50 / notino 79,90 -> median 77,20; cica: notino 55 / emag 65 -> median 60
    [cards] = [m.value for m in at.markdown if m.value.startswith('<div class="bc-stats">')]
    stores = re.findall(r'bc-stat-store">([^<]*)', cards)
    assert stores == ["eMAG", "Notino"]
    assert cards.count("cel mai ieftin la 1 din 2 produse") == 2
    assert "bc-legend" in markdown(at)
    assert list(matrix["Produs"]) == ["Cicaplast Baume B5+", "Effaclar Duo+"]
    assert list(matrix["eMAG"]) == ["+8,3%", "-3,5%"]
    assert list(matrix["Notino"]) == ["-8,3%", "+3,5%"]

    assert at.selectbox(key="cmp_store").value == "eMAG"
    assert list(detail["Produs"]) == ["Cicaplast Baume B5+", "Effaclar Duo+"]
    assert list(detail["Prețul magazinului"]) == ["65,00 lei", "74,50 lei"]
    assert list(detail["Median piață"]) == ["60,00 lei", "77,20 lei"]
    assert list(detail["Poziție"]) == ["Peste piață", "Sub piață"]
    assert "**eMAG**: 1 sub piață, 1 peste piață, din 2 listate." in markdown(at)

    at.selectbox(key="cmp_store").select("Notino").run()
    assert list(at.dataframe[1].value["Poziție"]) == ["Sub piață", "Peste piață"]


def test_competitor_view_out_of_stock_brand(ui_api: respx.MockRouter, shop: dict[str, int]) -> None:
    at = open_competitors()
    at.selectbox(key="cmp_brand").select("CeraVe").run()
    detail = at.dataframe[1].value
    assert list(detail["Poziție"]) == ["Stoc epuizat"]
    assert list(detail["Median piață"]) == ["—"]


def test_competitor_matrix_marks_unlisted_cells(
    ui_api: respx.MockRouter, shop: dict[str, int], api_session: Session
) -> None:
    sephora = Retailer(slug="sephora", name="Sephora", domain="sephora.ro")
    duo = api_session.get(Product, shop["duo"])
    assert duo is not None
    _observe(api_session, sephora, duo, "https://sephora.ro/duo", [(1, 9_000, True)])
    api_session.commit()
    at = open_competitors()
    at.selectbox(key="cmp_brand").select("La Roche-Posay").run()
    matrix = at.dataframe[0].value
    assert list(matrix["Produs"]) == ["Cicaplast Baume B5+", "Effaclar Duo+"]
    assert matrix["Sephora"][0] == "—"  # Sephora doesn't list Cicaplast
    assert matrix["Sephora"][1].startswith("+")


def test_competitor_view_without_brands(ui_api: respx.MockRouter) -> None:
    at = open_competitors()
    assert "Nu există încă branduri" in at.info[0].value
