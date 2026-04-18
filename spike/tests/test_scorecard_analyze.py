from __future__ import annotations

from spike.models import ParsedSample, Variant
from spike.scorecard.analyze import build_field_matrix, quality_tier


def _sample(retailer: str, **overrides) -> ParsedSample:
    defaults = dict(
        retailer_slug=retailer,
        source_url="https://x/y",
        raw_capture_id="cid",
        canonical_name="N",
        brand_name="B",
        current_price=100.0,
        current_price_raw="100",
        variants=[Variant(option_value="30ml", price=100.0)],
        ingredients_raw="water, glycerin",
        ingredients_source="text",
        description_raw="d",
        images=["http://img"],
        rating_raw="4.5 (10)",
        offers_raw=["offer A"],
        stock_status_raw="in_stock",
        missing_fields=set(),
    )
    defaults.update(overrides)
    return ParsedSample(**defaults)


def test_field_matrix_counts_presence_by_retailer() -> None:
    samples = [
        _sample("minimalist"),
        _sample("minimalist", ingredients_raw=None, missing_fields={"ingredients"}),
        _sample("nykaa"),
        _sample("nykaa", current_price=None, current_price_raw=None,
                missing_fields={"current_price"}),
    ]
    matrix = build_field_matrix(samples)
    ing_mini = next(r for r in matrix
                    if r.field_name == "ingredients" and r.retailer_slug == "minimalist")
    assert ing_mini.present_count == 1
    assert ing_mini.sample_count == 2

    price_nykaa = next(r for r in matrix
                       if r.field_name == "current_price" and r.retailer_slug == "nykaa")
    assert price_nykaa.present_count == 1
    assert price_nykaa.sample_count == 2


def test_quality_tier_classification() -> None:
    assert quality_tier(0.95) == "reliable"
    assert quality_tier(0.70) == "partial"
    assert quality_tier(0.20) == "unreliable"
    assert quality_tier(0.0) == "absent"
