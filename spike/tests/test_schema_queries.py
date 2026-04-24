from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://wand:wand@localhost:5433/wand_spike")
SPIKE_ROOT = Path(__file__).resolve().parent.parent


def _db_available() -> bool:
    dsn = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    try:
        conn = psycopg.connect(dsn, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


def _pg_conn():
    dsn = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(dsn)


def _load_schema(conn: psycopg.Connection, sql_path: Path) -> None:
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS core CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS users CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS scraping CASCADE")
        cur.execute(sql_path.read_text())
    conn.commit()


@pytest.fixture()
def db_v0():
    if not _db_available():
        pytest.skip("Postgres not available")
    with _pg_conn() as conn:
        _load_schema(conn, SPIKE_ROOT / "src" / "spike" / "schema" / "v0.sql")
        yield conn


def test_v0_loads_cleanly(db_v0: psycopg.Connection) -> None:
    with db_v0.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.products")
        assert cur.fetchone()[0] == 0


def test_v0_price_compare_query(db_v0: psycopg.Connection) -> None:
    """Cross-retailer minimum-price query — one of Phase 1's core reads."""
    with db_v0.cursor() as cur:
        cur.execute("INSERT INTO core.brands (name) VALUES ('Minimalist') RETURNING id")
        brand_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.products (brand_id, canonical_name) VALUES (%s, 'Niacinamide 10%%') RETURNING id",
            (brand_id,),
        )
        product_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.retailers (slug, name, base_url) VALUES ('minimalist', 'Minimalist', 'https://x'), ('nykaa', 'Nykaa', 'https://y') RETURNING id"
        )
        for (retailer_id,), price in zip(cur.fetchall(), [449.0, 499.0]):
            cur.execute(
                "INSERT INTO core.retailer_listings (product_id, retailer_id, listing_url, current_price) VALUES (%s, %s, %s, %s)",
                (product_id, retailer_id, "https://z", price),
            )

        cur.execute(
            """
            SELECT min(current_price) FROM core.retailer_listings
             WHERE product_id = %s AND current_price IS NOT NULL
            """,
            (product_id,),
        )
        assert cur.fetchone()[0] == 449.0
    db_v0.commit()


def test_v0_shelf_read_query(db_v0: psycopg.Connection) -> None:
    with db_v0.cursor() as cur:
        cur.execute("INSERT INTO core.brands (name) VALUES ('Plum') RETURNING id")
        brand_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.products (brand_id, canonical_name) VALUES (%s, 'Vitamin C Serum') RETURNING id",
            (brand_id,),
        )
        product_id = cur.fetchone()[0]
        cur.execute("INSERT INTO users.users (phone) VALUES ('+91-9999999999') RETURNING id")
        user_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO users.shelf_items (user_id, product_id) VALUES (%s, %s)",
            (user_id, product_id),
        )
        cur.execute(
            """
            SELECT p.canonical_name FROM users.shelf_items si
              JOIN core.products p ON p.id = si.product_id
             WHERE si.user_id = %s
            """,
            (user_id,),
        )
        assert [r[0] for r in cur.fetchall()] == ["Vitamin C Serum"]
    db_v0.commit()


def test_v0_search_query_uses_trgm(db_v0: psycopg.Connection) -> None:
    with db_v0.cursor() as cur:
        cur.execute("INSERT INTO core.brands (name) VALUES ('The Derma Co') RETURNING id")
        brand_id = cur.fetchone()[0]
        for name in ["1% Kojic Acid Face Serum", "2% Salicylic Face Wash", "Vitamin C Face Moisturizer"]:
            cur.execute(
                "INSERT INTO core.products (brand_id, canonical_name) VALUES (%s, %s)",
                (brand_id, name),
            )

        cur.execute(
            "SELECT canonical_name FROM core.products WHERE canonical_name %% 'vitamin c'"
        )
        names = [r[0] for r in cur.fetchall()]
        assert any("Vitamin C" in n for n in names)
    db_v0.commit()


@pytest.fixture()
def db_v1():
    if not _db_available():
        pytest.skip("Postgres not available")
    with _pg_conn() as conn:
        _load_schema(conn, SPIKE_ROOT / "src" / "spike" / "schema" / "v1.sql")
        yield conn


def test_v1_loads_cleanly(db_v1: psycopg.Connection) -> None:
    with db_v1.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.products")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM scraping.ingredient_extraction_queue")
        assert cur.fetchone()[0] == 0


def test_v1_rating_columns_queryable(db_v1: psycopg.Connection) -> None:
    """Delta 4: rating split into value+count — verify they're independently queryable."""
    with db_v1.cursor() as cur:
        cur.execute("INSERT INTO core.brands (name) VALUES ('Purplle Brand') RETURNING id")
        brand_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.products (brand_id, canonical_name) VALUES (%s, 'Vitamin C Serum') RETURNING id",
            (brand_id,),
        )
        product_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.retailers (slug, name, base_url) VALUES ('purplle', 'Purplle', 'https://purplle.com') RETURNING id"
        )
        retailer_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.retailer_listings (product_id, retailer_id, listing_url, current_price, rating_value, rating_count) "
            "VALUES (%s, %s, %s, 499.0, 4.3, 212) RETURNING id",
            (product_id, retailer_id, "https://purplle.com/p/x"),
        )
        cur.execute(
            "SELECT rating_value, rating_count FROM core.retailer_listings WHERE product_id = %s",
            (product_id,),
        )
        row = cur.fetchone()
        assert float(row[0]) == 4.3
        assert row[1] == 212
    db_v1.commit()


def test_v1_ingredient_queue_tracks_pending(db_v1: psycopg.Connection) -> None:
    """Delta 2: ingredient_extraction_queue — every product starts as pending."""
    with db_v1.cursor() as cur:
        cur.execute("INSERT INTO core.brands (name) VALUES ('Minimalist') RETURNING id")
        brand_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.products (brand_id, canonical_name, ingredient_scrape_status) "
            "VALUES (%s, 'Niacinamide 10%%', 'pending') RETURNING id",
            (brand_id,),
        )
        product_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.retailers (slug, name, base_url) VALUES ('minimalist', 'Minimalist', 'https://beminimalist.co') RETURNING id"
        )
        retailer_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.retailer_listings (product_id, retailer_id, listing_url) VALUES (%s, %s, %s) RETURNING id",
            (product_id, retailer_id, "https://beminimalist.co/p/x"),
        )
        listing_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO scraping.ingredient_extraction_queue (product_id, listing_id) VALUES (%s, %s)",
            (product_id, listing_id),
        )
        cur.execute(
            "SELECT status FROM scraping.ingredient_extraction_queue WHERE product_id = %s",
            (product_id,),
        )
        assert cur.fetchone()[0] == 'pending'
    db_v1.commit()
