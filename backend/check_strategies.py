"""Check what ingredient extraction strategies exist for the 5 brands."""
from pathlib import Path
import psycopg
from dotenv import load_dotenv
load_dotenv(Path(".env"))
from app.config import settings

DSN = settings.database_url.replace("postgresql+psycopg://", "postgresql://")

with psycopg.connect(DSN) as conn:
    with conn.cursor() as cur:
        # First check the schema of ingredient_strategies
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'scraping' AND table_name = 'ingredient_strategies'
            ORDER BY ordinal_position
        """)
        cols = cur.fetchall()
        print("INGREDIENT_STRATEGIES SCHEMA:")
        for c in cols:
            print(f"  {c[0]}: {c[1]}")

        print()

        # Check strategies with proper columns
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'scraping' AND table_name = 'ingredient_strategies'
        """)
        col_names = [r[0] for r in cur.fetchall()]
        print(f"Columns: {col_names}")
        print()

        # Fetch all strategies
        cur.execute("SELECT * FROM scraping.ingredient_strategies LIMIT 30")
        rows = cur.fetchall()
        print(f"STRATEGIES (all {len(rows)}):")
        for row in rows:
            print(f"  {row}")
