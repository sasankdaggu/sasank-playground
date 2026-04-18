from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from spike.models import ParsedSample, RawCapture


def capture_id(rc: RawCapture) -> str:
    """Stable ID derived from source_url + fetched_at — used as filename."""
    key = f"{rc.retailer_slug}:{rc.source_url}:{rc.fetched_at.isoformat()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def persist_raw(rc: RawCapture, raw_dir: Path) -> str:
    cid = capture_id(rc)
    retailer_dir = raw_dir / rc.retailer_slug
    retailer_dir.mkdir(parents=True, exist_ok=True)
    (retailer_dir / f"{cid}.json").write_text(rc.model_dump_json(indent=2))
    return cid


def persist_parsed(ps: ParsedSample, parsed_dir: Path) -> None:
    retailer_dir = parsed_dir / ps.retailer_slug
    retailer_dir.mkdir(parents=True, exist_ok=True)
    key = f"{ps.raw_capture_id}:{ps.source_url}"
    filename = hashlib.sha256(key.encode()).hexdigest()[:16]
    (retailer_dir / f"{filename}.json").write_text(ps.model_dump_json(indent=2))


class Sampler(Protocol):
    """A sampler produces ParsedSample instances and persists RawCapture side-effects."""

    async def sample(self, n: int, raw_dir: Path, parsed_dir: Path) -> list[ParsedSample]: ...
