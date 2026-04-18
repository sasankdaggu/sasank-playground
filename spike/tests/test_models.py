from __future__ import annotations

from datetime import datetime, timezone

from spike.models import ParsedSample, RawCapture


def test_raw_capture_roundtrip_json() -> None:
    rc = RawCapture(
        retailer_slug="minimalist",
        source_url="https://beminimalist.co/products/niacinamide",
        tier_used="shopify",
        fetched_at=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
        fetcher_version="spike-0.0.1",
        content_type="application/json",
        body="{\"product\": {}}",
        http_status=200,
    )
    blob = rc.model_dump_json()
    restored = RawCapture.model_validate_json(blob)
    assert restored == rc


def test_parsed_sample_tracks_missing_fields_explicitly() -> None:
    ps = ParsedSample(
        retailer_slug="nykaa",
        source_url="https://www.nykaa.com/x",
        raw_capture_id="abc123",
        canonical_name="Example serum",
        brand_name="Brand",
        category_hint="face",
        current_price=None,
        current_price_raw="Currently unavailable",
        compare_at_price=None,
        stock_status_raw=None,
        variants=[],
        ingredients_raw=None,
        ingredients_source=None,
        description_raw=None,
        images=[],
        rating_raw=None,
        offers_raw=[],
        missing_fields={"current_price", "stock_status", "ingredients", "rating"},
    )
    assert "current_price" in ps.missing_fields
    assert ps.current_price_raw == "Currently unavailable"
