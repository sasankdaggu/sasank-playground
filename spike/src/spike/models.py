from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TierLabel = Literal["shopify", "marketplace-selector", "marketplace-html"]


class RawCapture(BaseModel):
    """Immutable verbatim capture of a source response."""

    retailer_slug: str
    source_url: str
    tier_used: TierLabel
    fetched_at: datetime
    fetcher_version: str
    content_type: str
    body: str
    http_status: int


class Variant(BaseModel):
    option_name: str | None = None
    option_value: str | None = None
    sku: str | None = None
    price: float | None = None
    compare_at_price: float | None = None
    available: bool | None = None


class ParsedSample(BaseModel):
    """What each sampler produces. Fields tracked explicitly even when missing."""

    retailer_slug: str
    source_url: str
    raw_capture_id: str

    canonical_name: str | None = None
    brand_name: str | None = None
    category_hint: str | None = None

    current_price: float | None = None
    current_price_raw: str | None = None
    compare_at_price: float | None = None

    stock_status_raw: str | None = None

    variants: list[Variant] = Field(default_factory=list)

    ingredients_raw: str | None = None
    ingredients_source: Literal["text", "image", "pdf", None] = None

    description_raw: str | None = None
    images: list[str] = Field(default_factory=list)

    rating_raw: str | None = None

    offers_raw: list[str] = Field(default_factory=list)

    missing_fields: set[str] = Field(default_factory=set)


class FieldPresence(BaseModel):
    """Row in the field × retailer matrix."""

    field_name: str
    retailer_slug: str
    present_count: int
    sample_count: int
    notes: str | None = None

    @property
    def presence_ratio(self) -> float:
        return self.present_count / self.sample_count if self.sample_count else 0.0
