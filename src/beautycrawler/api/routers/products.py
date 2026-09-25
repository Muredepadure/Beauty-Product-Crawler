import json
from importlib import resources
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(tags=["products"])

# Resolved relative to the installed package, so the API works from any CWD.
DATA_FILE = resources.files("beautycrawler").joinpath("data/products.json")


def load_products() -> list[dict[str, Any]]:
    with DATA_FILE.open("r", encoding="utf-8-sig") as f:  # tolerate a BOM
        data: list[dict[str, Any]] = json.load(f)
    return data


PRODUCTS = load_products()


def normalize(s: str) -> str:
    return " ".join(s.lower().split())


@router.get("/products")
def list_products(
    q: str | None = Query(None, description="Free text search over name/brand"),
    brand: str | None = None,
    category: str | None = None,
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    items = PRODUCTS
    if q:
        nq = normalize(q)
        items = [p for p in items if nq in normalize(p["name"]) or nq in normalize(p["brand"])]
    if brand:
        nb = normalize(brand)
        items = [p for p in items if nb == normalize(p["brand"])]
    if category:
        nc = normalize(category)
        items = [p for p in items if nc == normalize(p.get("category", ""))]

    total = len(items)
    items = items[offset : offset + limit]
    return {"total": total, "items": items}
