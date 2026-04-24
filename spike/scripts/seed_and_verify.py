"""Load v1 schema, seed with spike samples, verify canonical queries.

Usage:
  cd spike
  docker compose -f ../docker-compose.yml up -d   # start Postgres first
  python scripts/seed_and_verify.py
"""
from __future__ import annotations

from pathlib import Path

import structlog
from dotenv import load_dotenv

from spike.schema.seed import (
    _conn,
    load_all_samples,
    load_schema,
    seed_retailers,
    seed_sample,
    verify_queries,
)

SPIKE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(SPIKE_ROOT / ".env")
log = structlog.get_logger()

V1_SCHEMA = SPIKE_ROOT / "src" / "spike" / "schema" / "v1.sql"
PARSED_DIR = SPIKE_ROOT / "data" / "parsed"


def main() -> None:
    conn = _conn()
    log.info("connected_to_db")

    log.info("loading_v1_schema")
    load_schema(conn, V1_SCHEMA)

    log.info("seeding_retailers")
    retailer_ids = seed_retailers(conn)

    samples = load_all_samples(PARSED_DIR)
    log.info("seeding_samples", count=len(samples))
    seeded = 0
    for ps in samples:
        try:
            seed_sample(conn, ps, retailer_ids)
            seeded += 1
        except Exception as e:
            log.warning("seed_failed", url=ps.source_url, error=str(e))

    log.info("seed_complete", seeded=seeded, total=len(samples))

    log.info("verifying_queries")
    verify_queries(conn)

    conn.close()
    print(f"\nSeeded {seeded}/{len(samples)} samples. v1 schema verified.")
    print("Spike complete. Deliverables in spike/data/reports/ and spike/memo/")


if __name__ == "__main__":
    main()
