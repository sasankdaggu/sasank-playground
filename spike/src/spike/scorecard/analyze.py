from __future__ import annotations

from collections import defaultdict
from typing import Literal

from spike.models import FieldPresence, ParsedSample

TRACKED_FIELDS: tuple[str, ...] = (
    "canonical_name",
    "brand_name",
    "category_hint",
    "current_price",
    "compare_at_price",
    "stock_status",
    "variants",
    "ingredients",
    "description",
    "images",
    "rating",
    "offers",
)

QualityTier = Literal["reliable", "partial", "unreliable", "absent"]


def _field_is_present(sample: ParsedSample, field: str) -> bool:
    if field in sample.missing_fields:
        return False
    match field:
        case "canonical_name": return sample.canonical_name is not None
        case "brand_name": return sample.brand_name is not None
        case "category_hint": return sample.category_hint is not None
        case "current_price": return sample.current_price is not None
        case "compare_at_price": return sample.compare_at_price is not None
        case "stock_status": return sample.stock_status_raw is not None
        case "variants": return len(sample.variants) > 0
        case "ingredients": return sample.ingredients_raw is not None
        case "description": return sample.description_raw is not None
        case "images": return len(sample.images) > 0
        case "rating": return sample.rating_raw is not None
        case "offers": return len(sample.offers_raw) > 0
    return False


def build_field_matrix(samples: list[ParsedSample]) -> list[FieldPresence]:
    counts: dict[tuple[str, str], tuple[int, int]] = defaultdict(lambda: (0, 0))
    for s in samples:
        for f in TRACKED_FIELDS:
            present, total = counts[(f, s.retailer_slug)]
            present += 1 if _field_is_present(s, f) else 0
            total += 1
            counts[(f, s.retailer_slug)] = (present, total)
    return [
        FieldPresence(field_name=f, retailer_slug=r, present_count=p, sample_count=t)
        for (f, r), (p, t) in sorted(counts.items())
    ]


def quality_tier(ratio: float) -> QualityTier:
    if ratio >= 0.90: return "reliable"
    if ratio >= 0.50: return "partial"
    if ratio > 0.0: return "unreliable"
    return "absent"
