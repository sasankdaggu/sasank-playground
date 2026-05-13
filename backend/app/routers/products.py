from __future__ import annotations

from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_conn
from app.schemas.product import ProductDetail, ProductSearchResult
from app.services import products as svc

router = APIRouter(prefix="/products", tags=["products"])

Conn = Annotated[psycopg.AsyncConnection, Depends(get_conn)]


@router.get("/filters")
async def get_filters(
    conn: Conn,
    q: str | None = Query(None),
    brand_id: list[int] = Query(default=[]),
    product_type: str | None = Query(None),
) -> dict:
    return await svc.get_filters(conn, q, brand_id, product_type)


@router.get("", response_model=ProductSearchResult)
async def search_products(
    conn: Conn,
    q: str | None = Query(None, description="Text search"),
    category: str | None = Query(None, description="Category slug"),
    brand_id: list[int] = Query(default=[], description="Brand ID filter (repeatable)"),
    product_type: str | None = Query(None, description="'singles' to hide bundles/packs"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
) -> ProductSearchResult:
    return await svc.search_products(conn, q, category, brand_id, product_type, page, page_size)


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(product_id: int, conn: Conn) -> ProductDetail:
    product = await svc.get_product(conn, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
