from __future__ import annotations

from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_conn

router = APIRouter(prefix="/ingredients", tags=["ingredients"])

Conn = Annotated[psycopg.AsyncConnection, Depends(get_conn)]


@router.get("/search")
async def search(conn: Conn, q: str = "", limit: int = 25) -> dict:
    if not q:
        return {"results": []}
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT i.id, i.inci_name, i.common_name,
                   d.id_rating, d.confidence_score
            FROM core.ingredients i
            LEFT JOIN core.ingredient_detail d ON d.ingredient_id = i.id
            WHERE i.inci_name ILIKE %s
            ORDER BY i.inci_name
            LIMIT %s
        """, (f"%{q}%", limit))
        rows = await cur.fetchall()
    return {"results": rows}


@router.get("/{ingredient_id}")
async def get_ingredient(ingredient_id: int, conn: Conn) -> dict:
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT i.id, i.inci_name, i.common_name, i.ingredient_category, i.concern_tags,
                   d.cas_number, d.ec_number, d.description, d.description_source,
                   d.functions, d.id_rating,
                   d.ewg_hazard_low, d.ewg_hazard_high, d.ewg_concerns,
                   d.cosdna_acne, d.cosdna_irritant,
                   d.cosing_annex, d.cosing_restriction,
                   d.sources_used, d.citation_urls, d.confidence_score, d.collated_at
            FROM core.ingredients i
            LEFT JOIN core.ingredient_detail d ON d.ingredient_id = i.id
            WHERE i.id = %s
        """, (ingredient_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Ingredient not found")

        # Per-source citations with their full payloads
        await cur.execute("""
            SELECT source, source_url, fetch_status, fetched_at,
                   description, functions, id_rating, raw_payload
            FROM core.ingredient_detail_sources
            WHERE ingredient_id = %s
            ORDER BY source
        """, (ingredient_id,))
        sources = await cur.fetchall()

        # Products that contain this ingredient
        await cur.execute("""
            SELECT p.id, p.canonical_name AS name, b.name AS brand_name, pi.position
            FROM core.product_ingredients pi
            JOIN core.products p ON p.id = pi.product_id
            JOIN core.brands b ON b.id = p.brand_id
            WHERE pi.ingredient_id = %s
            ORDER BY pi.position NULLS LAST, p.canonical_name
            LIMIT 50
        """, (ingredient_id,))
        used_in = await cur.fetchall()

    return {"ingredient": row, "sources": sources, "used_in_products": used_in}
