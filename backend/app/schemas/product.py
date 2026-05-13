from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class RetailerListing(BaseModel):
    retailer_id: int
    retailer_name: str
    retailer_slug: str
    listing_url: str
    current_price: Decimal | None
    compare_at_price: Decimal | None
    stock_status: str
    rating_value: float | None
    rating_count: int | None
    last_scraped_at: str | None


class ProductSummary(BaseModel):
    id: int
    canonical_name: str
    brand_name: str
    images: list[str]
    min_price: Decimal | None
    max_price: Decimal | None
    retailer_count: int
    ingredient_scrape_status: str


class ProductDetail(BaseModel):
    id: int
    canonical_name: str
    brand_name: str
    brand_id: int
    images: list[str]
    variants: list[dict]
    description_raw: str | None
    description_source: str | None
    ingredient_scrape_status: str
    ingredients_raw: str | None
    listings: list[RetailerListing]
    category: str | None


class ProductSearchResult(BaseModel):
    items: list[ProductSummary]
    total: int
    page: int
    page_size: int
