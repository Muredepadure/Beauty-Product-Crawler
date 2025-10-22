import json
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Query

router = APIRouter(tags=["products"])

DATA_PATH = Path("data/products.json")
with DATA_PATH.open("r", encoding="utf-8-sig") as f:  # note utf-8-sig
    PRODUCTS = json.load(f)


def normalize(s: str) -> str:
    return " ".join(s.lower().split())

@router.get("/products")
def list_products(
    q: Optional[str] = Query(None, description="Free text search over name/brand"),
    brand: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 24,
    offset: int = 0,
):
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
