"""Parse `core.products.ingredients_raw` (free-text INCI list) into normalized
`core.ingredients` rows + `core.product_ingredients` link rows.

Run:
  python -m scraper.parse_inci
"""
from __future__ import annotations

import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

import asyncio  # noqa: E402

import psycopg  # noqa: E402

from app.config import settings  # noqa: E402

# Strip leading "Ingredients:" / "INCI:" / parenthetical numbers / asterisks
_LEAD_LABEL = re.compile(r"^\s*(ingredients?|inci( name)?|active ingredients?)\s*[:\-]\s*", re.IGNORECASE)
_PAREN_NUM = re.compile(r"\s*\([\d.,%\s\-]+\)\s*$")
_ASTERISK_TAIL = re.compile(r"\s*\*+\s*$")
_WORD_JOINER = re.compile(r"[\u2060\u200b\u200c\u200d\ufeff]")
_MULTISPACE = re.compile(r"\s+")


def _normalize(name: str) -> str:
    n = _WORD_JOINER.sub("", name).strip()
    n = _PAREN_NUM.sub("", n)
    n = _ASTERISK_TAIL.sub("", n)
    n = _MULTISPACE.sub(" ", n)
    return n.strip(" .,;:-").lower()


def _split_inci(raw: str) -> list[str]:
    """Split a raw INCI string into individual ingredient names."""
    if not raw:
        return []
    text = _LEAD_LABEL.sub("", raw)
    # Body Shop / Mamaearth use bullets / line-breaks; commas are universal
    text = re.sub(r"[•\u2022\n\r\t]+", ",", text)
    text = _WORD_JOINER.sub("", text)
    # Compound joins: "X (and) Y" or "X and Y" between INCI names → split on comma
    text = re.sub(r"\s*\(\s*and\s*\)\s*", ", ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+and\s+(?=[A-Z])", ", ", text)
    parts = []
    depth = 0
    buf = []
    for ch in text:
        if ch == "(":
            depth += 1; buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1); buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf)); buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))

    cleaned = []
    for p in parts:
        n = _normalize(p)
        if not n or len(n) > 200:
            continue
        if n.isdigit():
            continue
        if any(skip in n for skip in ("note:", "may contain", "see back", "refer to", "please refer")):
            continue
        cleaned.append(n)
    return cleaned


async def main() -> None:
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=psycopg.rows.dict_row) as conn:
        async with conn.cursor() as cur:
            sql = """
                SELECT id, ingredients_raw
                FROM core.products
                WHERE ingredients_raw IS NOT NULL AND LENGTH(ingredients_raw) > 20
            """
            if limit > 0:
                sql += f" LIMIT {limit}"
            await cur.execute(sql)
            products = await cur.fetchall()

        print(f"Parsing INCI for {len(products)} products", flush=True)

        # Build a lowercase-INCI cache to dedupe
        ingredient_cache: dict[str, int] = {}
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, lower(inci_name) AS k FROM core.ingredients")
            for r in await cur.fetchall():
                ingredient_cache[r["k"]] = r["id"]

        new_ingredients = 0
        new_links = 0
        for batch_start in range(0, len(products), 50):
            batch = products[batch_start: batch_start + 50]
            async with conn.cursor() as cur:
                for p in batch:
                    names = _split_inci(p["ingredients_raw"])
                    if not names:
                        continue
                    await cur.execute("DELETE FROM core.product_ingredients WHERE product_id = %s", (p["id"],))
                    for pos, name in enumerate(names, start=1):
                        ing_id = ingredient_cache.get(name)
                        if ing_id is None:
                            await cur.execute(
                                "INSERT INTO core.ingredients (inci_name) VALUES (%s) ON CONFLICT (inci_name) DO NOTHING RETURNING id",
                                (name,)
                            )
                            row = await cur.fetchone()
                            if row:
                                ing_id = row["id"]
                                new_ingredients += 1
                            else:
                                # Conflict: another batch already inserted it
                                await cur.execute("SELECT id FROM core.ingredients WHERE lower(inci_name) = %s", (name,))
                                ing_id = (await cur.fetchone())["id"]
                            ingredient_cache[name] = ing_id
                        await cur.execute("""
                            INSERT INTO core.product_ingredients (product_id, ingredient_id, position)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """, (p["id"], ing_id, pos))
                        new_links += 1
            await conn.commit()
            print(f"  batch {batch_start//50 + 1}/{(len(products)+49)//50} committed "
                  f"(ingredients={new_ingredients}, links={new_links})", flush=True)

        print(f"DONE — {new_ingredients} ingredients, {new_links} links", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
