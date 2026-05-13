import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv(override=True)
import psycopg, psycopg.rows
from app.config import settings

DB_URL = os.environ.get("DATABASE_URL", settings.database_url).replace("postgresql+psycopg://", "postgresql://")

async def main():
    async with await psycopg.AsyncConnection.connect(DB_URL, row_factory=psycopg.rows.dict_row) as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT p.id, p.canonical_name, b.name as brand_name, p.shelf_url, p.thumb_url
                FROM core.products p
                JOIN core.brands b ON b.id = p.brand_id
                WHERE p.shelf_url IS NOT NULL
                LIMIT 6
            """)
            rows = await cur.fetchall()
    for r in rows:
        print(f"\n{r['brand_name']} — {r['canonical_name'][:40]}")
        print(f"  shelf (transparent): {r['shelf_url']}")
        print(f"  thumb (cream bg):    {r['thumb_url']}")

asyncio.run(main())
