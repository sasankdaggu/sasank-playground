"""Check ingredient extraction strategies for the 5 brands by domain."""
from pathlib import Path
import psycopg
from dotenv import load_dotenv
load_dotenv(Path(".env"))
from app.config import settings

DSN = settings.database_url.replace("postgresql+psycopg://", "postgresql://")

BRAND_DOMAINS = {
    'plix':      ['plixlife.com'],
    'mamaearth': ['mamaearth.in'],
    'pixi_in':   ['in.pixibeauty.com', 'pixibeauty.com'],
    'pilgrim':   ['discoverpilgrim.com'],
    'plum':      ['plumgoodness.com'],
}

with psycopg.connect(DSN) as conn:
    with conn.cursor() as cur:
        # Check strategies
        all_domains = [d for ds in BRAND_DOMAINS.values() for d in ds]
        cur.execute("""
            SELECT brand_domain, brand_name, css_selector, requires_js, status, notes, sample_inci_preview
            FROM scraping.ingredient_strategies
            WHERE brand_domain = ANY(%s)
            ORDER BY brand_domain
        """, (all_domains,))
        rows = cur.fetchall()
        print("STRATEGIES for target brands:")
        for row in rows:
            print(f"\n  Domain:  {row[0]} ({row[1]})")
            print(f"  Status:  {row[4]}")
            print(f"  Selector:{row[2]}")
            print(f"  Req JS:  {row[3]}")
            print(f"  Notes:   {str(row[5])[:200]}")
            print(f"  Preview: {str(row[6])[:200]}")

        if not rows:
            print("  No strategies found for these domains!")
            print("\nAll brand_domains in strategies:")
            cur.execute("SELECT DISTINCT brand_domain, brand_name, status FROM scraping.ingredient_strategies ORDER BY brand_domain")
            for r in cur.fetchall():
                print(f"  {r[0]} ({r[1]}): {r[2]}")

        # Queue counts
        print("\n\nQUEUE STATUS by retailer slug:")
        cur.execute("""
            SELECT r.slug, q.status, COUNT(*)
            FROM scraping.ingredient_extraction_queue q
            JOIN core.retailer_listings rl ON rl.id = q.listing_id
            JOIN core.retailers r ON r.id = rl.retailer_id
            WHERE r.slug IN ('plix', 'mamaearth', 'pixi_in', 'pilgrim', 'plum')
            GROUP BY r.slug, q.status
            ORDER BY r.slug, q.status
        """)
        for row in cur.fetchall():
            print(f"  {row[0]:15s} {row[1]:25s} {row[2]:6d}")

        # How does the extractor find strategies (by retailer_slug → brand_domain mapping?)
        print("\n\nRETAILER table - website fields for these brands:")
        cur.execute("""
            SELECT r.slug, r.name, r.website_url
            FROM core.retailers r
            WHERE r.slug IN ('plix', 'mamaearth', 'pixi_in', 'pilgrim', 'plum')
        """)
        for row in cur.fetchall():
            print(f"  {row[0]:15s} {row[1]:25s} {row[2]}")
