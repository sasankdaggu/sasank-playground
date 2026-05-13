"""
One-shot script: process all product images — remove background, upload 3 variants to R2.
Run after R2 + REMOVEBG_API_KEY are in .env:
  cd backend && .venv/bin/python scripts/migrate_images_to_r2.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=True)

import psycopg
import psycopg.rows
from app.config import settings
from app.services.storage import process_and_upload

_raw_db_url = os.environ.get("DATABASE_URL", settings.database_url)
DB_URL = _raw_db_url.replace("postgresql+psycopg://", "postgresql://")


async def main() -> None:
    if not settings.r2_account_id:
        print("R2 not configured — set R2_ACCOUNT_ID etc. in .env")
        return

    print(f"DB: {DB_URL.split('@')[-1].split('/')[0]}")
    print(f"Remove.bg: {'configured' if settings.removebg_api_key else 'NOT configured — will upload originals only'}")

    async with await psycopg.AsyncConnection.connect(DB_URL, row_factory=psycopg.rows.dict_row) as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, images FROM core.products WHERE images != '[]'::jsonb")
            rows = await cur.fetchall()

    print(f"\nProcessing {len(rows)} products...")

    async with await psycopg.AsyncConnection.connect(DB_URL, row_factory=psycopg.rows.dict_row) as conn:
        for i, row in enumerate(rows, 1):
            images: list[str] = row["images"] or []
            if not images:
                continue

            hero_url = images[0]

            # Skip if already processed
            if settings.r2_public_url and settings.r2_public_url in hero_url:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT thumb_url FROM core.products WHERE id = %s", (row["id"],))
                    existing = await cur.fetchone()
                    if existing and existing["thumb_url"]:
                        print(f"  [{i}/{len(rows)}] product {row['id']} already done, skipping")
                        continue

            print(f"  [{i}/{len(rows)}] product {row['id']} — processing hero image...")
            variants = await process_and_upload(hero_url)

            # Also migrate remaining images (originals only)
            other_originals = []
            for url in images[1:]:
                try:
                    r = await process_and_upload(url)
                    other_originals.append(r["original"])
                except Exception:
                    other_originals.append(url)

            all_originals = [variants["original"]] + other_originals

            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE core.products
                    SET images = %s, thumb_url = %s, shelf_url = %s
                    WHERE id = %s
                    """,
                    (json.dumps(all_originals), variants["thumb"], variants["shelf"], row["id"]),
                )
            await conn.commit()
            print(f"    thumb: {variants['thumb'][-40:]}")
            print(f"    shelf: {variants['shelf'][-40:]}")

    print(f"\nDone. {len(rows)} products processed.")


if __name__ == "__main__":
    asyncio.run(main())
