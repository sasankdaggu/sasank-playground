"""Shared data model for scraper output — common across all retailer types."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScrapedVariant:
    sku: str | None
    option_value: str | None  # e.g. "50ml", "100ml"
    price: float | None
    compare_at_price: float | None
    available: bool | None


@dataclass
class ScrapedProduct:
    retailer_slug: str
    source_url: str
    canonical_name: str | None
    brand_name: str | None
    category_hint: str | None
    current_price: float | None
    compare_at_price: float | None
    stock_status_raw: str | None
    variants: list[ScrapedVariant] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    description_raw: str | None = None
    description_source: str | None = None
    rating_raw: str | None = None
    ingredients_raw: str | None = None
    # Extended detail fields
    subcategory_hint: str | None = None
    pack_size: str | None = None
    how_to_use: str | None = None
    skin_type: list[str] = field(default_factory=list)
    skin_concerns: list[str] = field(default_factory=list)
    country_of_origin: str | None = None
    key_ingredients_raw: str | None = None
    claims: list[str] = field(default_factory=list)
    source_tags: list[str] | None = None
    missing_fields: set[str] = field(default_factory=set)
