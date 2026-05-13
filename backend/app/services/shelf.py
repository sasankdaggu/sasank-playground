from __future__ import annotations

import json

import psycopg

from app.schemas.shelf import ShelfItem, ShelfItemAdd, ShelfItemUpdate


async def get_shelf(conn: psycopg.AsyncConnection, user_id: int) -> list[ShelfItem]:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT
                si.id, si.product_id, si.added_at, si.opened_date,
                si.pct_remaining, si.user_rating, si.notes, si.purchase_price,
                p.canonical_name, b.name AS brand_name, p.images
            FROM users.shelf_items si
            JOIN core.products p ON p.id = si.product_id
            JOIN core.brands b ON b.id = p.brand_id
            WHERE si.user_id = %s
            ORDER BY si.added_at DESC
            """,
            (user_id,),
        )
        rows = await cur.fetchall()

    return [
        ShelfItem(
            id=r["id"],
            product_id=r["product_id"],
            canonical_name=r["canonical_name"],
            brand_name=r["brand_name"],
            images=r["images"] if isinstance(r["images"], list) else json.loads(r["images"] or "[]"),
            added_at=r["added_at"],
            opened_date=r["opened_date"],
            pct_remaining=r["pct_remaining"],
            user_rating=r["user_rating"],
            notes=r["notes"],
            purchase_price=r["purchase_price"],
        )
        for r in rows
    ]


async def add_to_shelf(
    conn: psycopg.AsyncConnection, user_id: int, payload: ShelfItemAdd
) -> ShelfItem:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO users.shelf_items
              (user_id, product_id, purchased_from_retailer_id, purchase_price)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, product_id) DO UPDATE
              SET purchased_from_retailer_id = EXCLUDED.purchased_from_retailer_id,
                  purchase_price = EXCLUDED.purchase_price
            RETURNING id, added_at
            """,
            (user_id, payload.product_id, payload.purchased_from_retailer_id, payload.purchase_price),
        )
        row = await cur.fetchone()
        await conn.commit()

    items = await get_shelf(conn, user_id)
    return next(i for i in items if i.id == row["id"])


async def update_shelf_item(
    conn: psycopg.AsyncConnection, user_id: int, item_id: int, payload: ShelfItemUpdate
) -> ShelfItem | None:
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        items = await get_shelf(conn, user_id)
        return next((i for i in items if i.id == item_id), None)

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    async with conn.cursor() as cur:
        await cur.execute(
            f"UPDATE users.shelf_items SET {set_clause} WHERE id = %s AND user_id = %s",
            list(updates.values()) + [item_id, user_id],
        )
        await conn.commit()

    items = await get_shelf(conn, user_id)
    return next((i for i in items if i.id == item_id), None)


async def remove_from_shelf(
    conn: psycopg.AsyncConnection, user_id: int, item_id: int
) -> bool:
    async with conn.cursor() as cur:
        await cur.execute(
            "DELETE FROM users.shelf_items WHERE id = %s AND user_id = %s",
            (item_id, user_id),
        )
        await conn.commit()
        return cur.rowcount > 0
