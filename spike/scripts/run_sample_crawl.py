"""Drive all samplers end-to-end. Writes data/raw/ + data/parsed/.

Usage:
  uv run python scripts/run_sample_crawl.py           # full 80-sample crawl
  uv run python scripts/run_sample_crawl.py --dry     # only Shopify (no proxy needed)
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import structlog
from dotenv import load_dotenv

from spike.config import RETAILERS, RetailerTier
from spike.samplers.marketplace import MarketplaceSampler
from spike.samplers.shopify import ShopifySampler

SPIKE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(SPIKE_ROOT / ".env")
log = structlog.get_logger()


async def main(dry: bool) -> None:
    n = int(os.getenv("SAMPLES_PER_RETAILER", "8"))
    raw_dir = SPIKE_ROOT / "data" / "raw"
    parsed_dir = SPIKE_ROOT / "data" / "parsed"

    for r in RETAILERS:
        if r.tier is RetailerTier.SHOPIFY:
            log.info("sampling_shopify", retailer=r.slug, n=n)
            sampler = ShopifySampler(r.slug)
            samples = await sampler.sample(n, raw_dir, parsed_dir)
            log.info("sampled", retailer=r.slug, count=len(samples))
        elif r.tier is RetailerTier.MARKETPLACE:
            if dry:
                log.info("skipping_marketplace_in_dry_mode", retailer=r.slug)
                continue
            log.info("sampling_marketplace", retailer=r.slug, n=n)
            sampler = MarketplaceSampler(r.slug)
            samples = await sampler.sample(n, raw_dir, parsed_dir)
            log.info("sampled", retailer=r.slug, count=len(samples))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="Shopify-only; no marketplaces")
    args = ap.parse_args()
    asyncio.run(main(dry=args.dry))
