"""Typed client for the BeautyCrawler API, used by the Streamlit UI (P7.5).

Responses are parsed into the API's own response models (`api.schemas`), so the UI and
the API can't silently drift apart: a changed field fails validation here, in tests.
The base URL comes from settings (`BEAUTYCRAWLER_API_BASE_URL`).
"""

from types import TracebackType
from typing import Any, Self, TypeVar

import httpx
from pydantic import BaseModel, TypeAdapter

from beautycrawler.api.schemas import (
    BrandComparison,
    BrandPage,
    PriceDropList,
    ProductDetail,
    ProductHistory,
    ProductPage,
    RetailerOut,
)
from beautycrawler.config import get_settings

M = TypeVar("M", bound=BaseModel)

_RETAILERS = TypeAdapter(list[RetailerOut])


class ApiError(Exception):
    """The API could not be reached or answered with an error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class NotFound(ApiError):
    pass


class ApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 15.0,
        http: httpx.Client | None = None,
    ) -> None:
        """`http` injects a ready client (with its own base URL), e.g. a test client."""
        if http is None:
            url = (base_url or get_settings().api_base_url).rstrip("/")
            http = httpx.Client(base_url=url, timeout=timeout)
        self._http = http

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        clean = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        try:
            response = self._http.get(path, params=clean)
        except httpx.HTTPError as exc:
            raise ApiError(f"API unreachable: {exc}") from exc
        if response.status_code == 404:
            raise NotFound(f"Not found: {path}", 404)
        if response.is_error:
            raise ApiError(
                f"API error {response.status_code}: {response.text}", response.status_code
            )
        return response.json()

    def _model(self, model: type[M], path: str, params: dict[str, Any] | None = None) -> M:
        return model.model_validate(self._get(path, params))

    # ----------------------------------------------------------------- endpoints

    def search_products(
        self,
        q: str | None = None,
        *,
        brand: str | None = None,
        category: str | None = None,
        sort: str = "name",
        page: int = 1,
        page_size: int = 24,
        min_price_bani: int | None = None,
        max_price_bani: int | None = None,
        in_stock: bool = False,
    ) -> ProductPage:
        params = {
            "q": q,
            "brand": brand,
            "category": category,
            "sort": sort,
            "page": page,
            "page_size": page_size,
            "min_price": min_price_bani,
            "max_price": max_price_bani,
            "in_stock": "true" if in_stock else None,
        }
        return self._model(ProductPage, "/products", params)

    def get_product(self, product_id: int) -> ProductDetail:
        return self._model(ProductDetail, f"/products/{product_id}")

    def get_history(self, product_id: int, days: int | None = None) -> ProductHistory:
        return self._model(ProductHistory, f"/products/{product_id}/history", {"days": days})

    def list_retailers(self) -> list[RetailerOut]:
        return _RETAILERS.validate_python(self._get("/retailers"))

    def list_brands(self, q: str | None = None, page: int = 1, page_size: int = 200) -> BrandPage:
        return self._model(BrandPage, "/brands", {"q": q, "page": page, "page_size": page_size})

    def compare(self, brand: str, page: int = 1, page_size: int = 100) -> BrandComparison:
        params = {"brand": brand, "page": page, "page_size": page_size}
        return self._model(BrandComparison, "/compare", params)

    def price_drops(self, min_pct: float = 10, hours: int = 24, limit: int = 50) -> PriceDropList:
        params = {"min_pct": min_pct, "hours": hours, "limit": limit}
        return self._model(PriceDropList, "/price-drops", params)


def format_lei(bani: int | None) -> str:
    """Romanian price display: 1234599 -> "12.345,99 lei"; None -> "—"."""
    if bani is None:
        return "—"
    lei, rest = divmod(abs(bani), 100)
    sign = "-" if bani < 0 else ""
    return f"{sign}{lei:,}".replace(",", ".") + f",{rest:02d} lei"
