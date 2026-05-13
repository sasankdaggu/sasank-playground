from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class ShelfItemAdd(BaseModel):
    product_id: int
    purchased_from_retailer_id: int | None = None
    purchase_price: Decimal | None = None


class ShelfItemUpdate(BaseModel):
    opened_date: date | None = None
    pct_remaining: int | None = None
    user_rating: float | None = None
    notes: str | None = None


class ShelfItem(BaseModel):
    id: int
    product_id: int
    canonical_name: str
    brand_name: str
    images: list[str]
    added_at: datetime
    opened_date: date | None
    pct_remaining: int | None
    user_rating: float | None
    notes: str | None
    purchase_price: Decimal | None
