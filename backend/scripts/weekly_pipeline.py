"""
Weekly catalog pipeline — scrape all brands, enrich category signals, assign canonical categories.

This script orchestrates the full catalog refresh:
  1. Shopify scrape  — all Shopify D2C brands (direct fetch, ScraperAPI fallback)
  2. Custom scrape   — all non-Shopify D2C brands (sitemap + HTML parsing)
  3. Collection signals — map Shopify products to brand collection categories
  4. Breadcrumbs      — scrape product detail page breadcrumbs for non-Shopify brands
  5. Category assignment — run keyword + signal-based canonical category assignment

Usage:
  python -m scripts.weekly_pipeline                  # run full pipeline
  python -m scripts.weekly_pipeline --skip-scrape    # skip scraping, only categorize
  python -m scripts.weekly_pipeline --shopify-only   # skip custom/non-Shopify scrape
  python -m scripts.weekly_pipeline --dry-run        # parse only, no DB writes

Cadence:
  Set up a cron job to run this weekly. Example (every Sunday at 2am):
    0 2 * * 0  cd /path/to/backend && .venv/bin/python -m scripts.weekly_pipeline >> logs/weekly_pipeline.log 2>&1

  Or use the --interval-days flag with an external scheduler to guard against double-runs.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import structlog
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

log = structlog.get_logger()


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    return url.replace("postgresql+psycopg://", "postgresql://")


def _run(cmd: list[str], label: str) -> bool:
    """Run a subprocess, stream output, return True on success."""
    log.info(f"pipeline_step_start", step=label, cmd=" ".join(cmd))
    start = time.time()
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent)
    elapsed = round(time.time() - start, 1)
    if result.returncode == 0:
        log.info("pipeline_step_done", step=label, elapsed_s=elapsed)
        return True
    else:
        log.error("pipeline_step_failed", step=label, returncode=result.returncode, elapsed_s=elapsed)
        return False


async def _snapshot(conn) -> dict:
    """Return current catalog stats for before/after comparison."""
    cur = await conn.execute("SELECT count(*) FROM core.products")
    total = (await cur.fetchone())["count"]
    cur = await conn.execute("SELECT count(*) FROM core.products WHERE canonical_category_id IS NOT NULL")
    categorized = (await cur.fetchone())["count"]
    cur = await conn.execute("SELECT count(*) FROM core.products WHERE category_raw IS NOT NULL")
    has_raw = (await cur.fetchone())["count"]
    return {"total": total, "categorized": categorized, "has_category_raw": has_raw}


def _print_summary(before: dict, after: dict) -> None:
    new_total = after["total"] - before["total"]
    new_cat = after["categorized"] - before["categorized"]
    pct = after["categorized"] / after["total"] * 100 if after["total"] else 0
    print("\n=== Weekly Pipeline Summary ===")
    print(f"  Products:     {before['total']} → {after['total']}  ({new_total:+d} new)")
    print(f"  Categorized:  {before['categorized']} → {after['categorized']}  ({new_cat:+d}) = {pct:.1f}%")
    print(f"  category_raw: {before['has_category_raw']} → {after['has_category_raw']}")
    print(f"  Run at: {datetime.now(timezone.utc).isoformat()}")
    print("================================\n")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Weekly Wand catalog pipeline")
    p.add_argument("--skip-scrape", action="store_true", help="Skip scraping steps, only run categorization")
    p.add_argument("--shopify-only", action="store_true", help="Only scrape Shopify brands (skip custom)")
    p.add_argument("--custom-only", action="store_true", help="Only scrape custom/non-Shopify brands (skip Shopify)")
    p.add_argument("--skip-collection-signals", action="store_true", help="Skip collection signal scraper")
    p.add_argument("--skip-breadcrumbs", action="store_true", help="Skip breadcrumb scraper for non-Shopify")
    p.add_argument("--dry-run", action="store_true", help="Pass --dry-run to scraper (no DB writes)")
    p.add_argument("--limit", type=int, default=2000, help="Max products per retailer (default: 2000)")
    return p.parse_args()


async def main() -> None:
    args = _parse_args()
    python = sys.executable

    conn = await psycopg.AsyncConnection.connect(_db_url(), row_factory=dict_row)
    before = await _snapshot(conn)
    await conn.close()
    log.info("pipeline_start", before=before)

    steps_ok: list[bool] = []

    if not args.skip_scrape:
        # Step 1: Shopify brands
        if not args.custom_only:
            cmd = [python, "-m", "scraper.run", "--tier", "shopify", "--limit", str(args.limit)]
            if args.dry_run:
                cmd.append("--dry-run")
            steps_ok.append(_run(cmd, "shopify_scrape"))

        # Step 2: Custom (non-Shopify) brands
        if not args.shopify_only:
            cmd = [python, "-m", "scraper.run", "--tier", "custom", "--limit", str(args.limit)]
            if args.dry_run:
                cmd.append("--dry-run")
            steps_ok.append(_run(cmd, "custom_scrape"))

    # Step 3: Collection signals (Shopify brand taxonomy)
    if not args.skip_collection_signals and not args.dry_run:
        steps_ok.append(_run([python, "-m", "scripts.scrape_collection_signals"], "collection_signals"))

    # Step 4: Breadcrumb signals (non-Shopify brand taxonomy)
    if not args.skip_breadcrumbs and not args.dry_run:
        steps_ok.append(_run([python, "-m", "scripts.scrape_breadcrumbs"], "breadcrumbs"))

    # Step 5: Canonical category assignment
    if not args.dry_run:
        steps_ok.append(_run([python, "-m", "scripts.assign_canonical_categories"], "assign_categories"))

    conn = await psycopg.AsyncConnection.connect(_db_url(), row_factory=dict_row)
    after = await _snapshot(conn)
    await conn.close()

    _print_summary(before, after)

    failed = steps_ok.count(False)
    if failed:
        log.error("pipeline_complete_with_errors", failed_steps=failed, total_steps=len(steps_ok))
        sys.exit(1)
    else:
        log.info("pipeline_complete", total_steps=len(steps_ok))


if __name__ == "__main__":
    asyncio.run(main())
