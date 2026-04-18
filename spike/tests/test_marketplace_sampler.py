from __future__ import annotations

import os
from pathlib import Path

import pytest

from spike.samplers.marketplace import MarketplaceSampler, parse_marketplace_html


def test_parse_marketplace_html_prefers_json_ld(sample_fixture_dir: Path) -> None:
    html = (sample_fixture_dir / "nykaa_sample.html").read_text()
    ps = parse_marketplace_html(
        html=html,
        retailer_slug="nykaa",
        source_url="https://www.nykaa.com/sample",
        raw_capture_id="fixture-1",
    )
    assert ps.canonical_name == "Sample Face Serum"
    assert ps.brand_name == "SampleBrand"
    assert ps.current_price == 499.0
    assert ps.stock_status_raw == "InStock"
    assert ps.rating_raw == "4.3 (212)"
    assert "Flat 10% on Nykaa Prepaid" in ps.offers_raw
    assert ps.ingredients_raw is not None
    assert "Niacinamide" in ps.ingredients_raw


def test_parse_marketplace_html_marks_missing_on_empty_doc() -> None:
    ps = parse_marketplace_html(
        html="<html><body>nothing here</body></html>",
        retailer_slug="nykaa",
        source_url="https://www.nykaa.com/x",
        raw_capture_id="fixture-2",
    )
    assert ps.canonical_name is None
    assert "canonical_name" in ps.missing_fields
    assert "current_price" in ps.missing_fields
    assert "ingredients" in ps.missing_fields


@pytest.mark.skipif(
    not os.getenv("PROXY_USER"),
    reason="Live marketplace fetch requires proxy creds",
)
async def test_live_nykaa_sample_fetch(tmp_path: Path) -> None:
    """Smoke test — runs only when proxy creds are configured."""
    sampler = MarketplaceSampler(retailer_slug="nykaa", max_samples=1)
    samples = await sampler.sample(
        n=1, raw_dir=tmp_path / "raw", parsed_dir=tmp_path / "parsed"
    )
    assert len(samples) == 1
    raw_files = list((tmp_path / "raw" / "nykaa").glob("*.json"))
    assert raw_files, "expected a raw capture file to be persisted"
