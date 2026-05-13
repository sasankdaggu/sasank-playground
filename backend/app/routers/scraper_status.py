from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends

from app.database import get_conn

router = APIRouter(prefix="/scraper-status", tags=["scraper-status"])

Conn = Annotated[psycopg.AsyncConnection, Depends(get_conn)]


# Catalog of every scraper we monitor. Each entry produces one card on the dashboard.
# (kind, target, label, group)
SCRAPER_CATALOG: list[tuple[str, str, str, str]] = [
    # Marketplaces
    ("retailer_discovery", "nykaa", "Nykaa Discovery", "Marketplaces"),
    ("retailer_discovery", "tira", "Tira Discovery", "Marketplaces"),
    ("retailer_discovery", "purplle", "Purplle Discovery", "Marketplaces"),
    ("retailer_discovery", "sephora_in", "Sephora India Discovery", "Marketplaces"),
    ("retailer_discovery", "amazon_in", "Amazon India Discovery", "Marketplaces"),
    # D2C brand discovery (Shopify products.json)
    ("d2c_discovery", "minimalist", "Minimalist (D2C)", "D2C Brands"),
    ("d2c_discovery", "the_derma_co", "The Derma Co (D2C)", "D2C Brands"),
    ("d2c_discovery", "plum", "Plum Goodness (D2C)", "D2C Brands"),
    ("d2c_discovery", "dot_and_key", "Dot & Key (D2C)", "D2C Brands"),
    ("d2c_discovery", "mcaffeine", "mCaffeine (D2C)", "D2C Brands"),
    # Per-brand INCI extractors
    ("ingredient_extract", "beminimalist.co", "Minimalist INCI", "INCI Extractors"),
    ("ingredient_extract", "thedermaco.com", "Derma Co INCI", "INCI Extractors"),
    ("ingredient_extract", "plumgoodness.com", "Plum INCI", "INCI Extractors"),
    ("ingredient_extract", "dotandkey.com", "Dot & Key INCI", "INCI Extractors"),
    ("ingredient_extract", "discoverpilgrim.com", "Pilgrim INCI", "INCI Extractors"),
    ("ingredient_extract", "faebeauty.in", "FAE Beauty INCI", "INCI Extractors"),
    ("ingredient_extract", "mamaearth.in", "Mamaearth INCI", "INCI Extractors"),
    ("ingredient_extract", "beyondbeyond.co.in", "Beyond Beyond INCI", "INCI Extractors"),
    ("ingredient_extract", "paulaschoice.in", "Paula's Choice INCI", "INCI Extractors"),
    ("ingredient_extract", "thebodyshop.in", "Body Shop INCI", "INCI Extractors"),
    ("ingredient_extract", "aveeno.in", "Aveeno INCI", "INCI Extractors"),
    # Ingredient detail sources
    ("ingredient_detail", "ewg", "EWG Skin Deep", "Ingredient Detail"),
    ("ingredient_detail", "incidecoder", "INCIDecoder", "Ingredient Detail"),
    ("ingredient_detail", "cosing", "EU CosIng", "Ingredient Detail"),
    ("ingredient_detail", "cosdna", "COSDNA", "Ingredient Detail"),
    # Schema detection
    ("schema_detection", "llm", "LLM Schema Detection", "Internal"),
]


def _summarize_runs(runs: list[dict]) -> dict:
    if not runs:
        return {
            "status": "not_monitored",
            "uptime_30d": None,
            "last_success_at": None,
            "history_30d": [],
        }
    total_runs = len(runs)
    successes = sum(1 for r in runs if r["status"] in ("success", "partial"))
    last_success = next((r["finished_at"] or r["started_at"] for r in runs
                         if r["status"] in ("success", "partial")), None)
    last_status = runs[0]["status"]
    if last_status in ("success", "partial"):
        operational = "operational"
    elif last_status == "failed":
        operational = "down"
    else:
        operational = "running"

    # Build per-day history bars (oldest → newest, 30 days)
    today = datetime.now(timezone.utc).date()
    by_day: dict[str, str] = {}
    for r in runs:
        d = (r["finished_at"] or r["started_at"]).date().isoformat()
        # Latest run per day wins (runs sorted newest first → keep first)
        if d not in by_day:
            by_day[d] = r["status"]
    history = []
    for offset in range(29, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        history.append({"date": day, "status": by_day.get(day, "no_run")})

    return {
        "status": operational,
        "uptime_30d": round(successes / total_runs * 100, 1),
        "last_success_at": last_success.isoformat() if last_success else None,
        "history_30d": history,
        "total_runs_30d": total_runs,
    }


@router.get("")
async def get_scraper_status(conn: Conn) -> dict:
    """Return health summary for every scraper in the catalog."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT scraper_kind, scraper_target, status, started_at, finished_at,
                   items_attempted, items_succeeded, items_failed, error_message
            FROM scraping.scraper_execution_logs
            WHERE started_at >= %s
            ORDER BY started_at DESC
        """, (cutoff,))
        all_runs = await cur.fetchall()

    by_target: dict[tuple[str, str], list[dict]] = {}
    for r in all_runs:
        key = (r["scraper_kind"], r["scraper_target"])
        by_target.setdefault(key, []).append(r)

    cards = []
    for kind, target, label, group in SCRAPER_CATALOG:
        summary = _summarize_runs(by_target.get((kind, target), []))
        cards.append({
            "kind": kind,
            "target": target,
            "label": label,
            "group": group,
            **summary,
        })

    operational = sum(1 for c in cards if c["status"] == "operational")
    down = sum(1 for c in cards if c["status"] == "down")
    not_monitored = sum(1 for c in cards if c["status"] == "not_monitored")

    return {
        "summary": {
            "operational": operational,
            "down": down,
            "not_monitored": not_monitored,
            "total": len(cards),
        },
        "scrapers": cards,
    }
