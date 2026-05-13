from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RetailerTier(str, Enum):
    SHOPIFY = "shopify"          # Tier 0 in spec §9.2
    MARKETPLACE = "marketplace"  # Tier 1


@dataclass(frozen=True)
class Retailer:
    slug: str
    name: str
    tier: RetailerTier
    base_url: str
    products_json_url: str | None = None       # Shopify only
    sample_product_urls: tuple[str, ...] = field(default_factory=tuple)  # Marketplace only
    needs_proxy: bool = False
    # Lower = higher image quality priority. Used when merging images across retailers.
    # D2C brand sites have official photography; marketplaces vary.
    image_priority: int = 99
    # Whether this retailer can create a new canonical product row.
    # Amazon is pricing/purchase only — never a product source.
    # Non-D2C retailers only create products if no higher-priority source exists.
    can_create_canonical: bool = True
    # Priority for creating canonical products (1=always, 2=if no D2C, 3=last resort).
    catalog_priority: int = 99


RETAILERS: tuple[Retailer, ...] = (
    # --- Shopify D2C (Tier 0) ---
    Retailer(
        slug="minimalist", name="Minimalist", tier=RetailerTier.SHOPIFY,
        base_url="https://beminimalist.co",
        products_json_url="https://beminimalist.co/products.json",
        image_priority=1, catalog_priority=1,
    ),
    Retailer(
        slug="plum", name="Plum Goodness", tier=RetailerTier.SHOPIFY,
        base_url="https://plumgoodness.com",
        products_json_url="https://plumgoodness.com/products.json",
        image_priority=1, catalog_priority=1,
    ),
    Retailer(
        slug="mcaffeine", name="mCaffeine", tier=RetailerTier.SHOPIFY,
        base_url="https://mcaffeine.com",
        products_json_url="https://mcaffeine.com/products.json",
        image_priority=1, catalog_priority=1,
    ),
    Retailer(
        slug="dot_and_key", name="Dot & Key", tier=RetailerTier.SHOPIFY,
        base_url="https://dotandkey.com",
        products_json_url="https://dotandkey.com/products.json",
        image_priority=1, catalog_priority=1,
    ),
    Retailer(
        slug="the_derma_co", name="The Derma Co", tier=RetailerTier.SHOPIFY,
        base_url="https://thedermaco.com",
        products_json_url="https://thedermaco.com/products.json",
        image_priority=1, catalog_priority=1,
    ),
    # --- Marketplaces (Tier 1) ---
    Retailer(
        slug="nykaa", name="Nykaa", tier=RetailerTier.MARKETPLACE,
        base_url="https://www.nykaa.com",
        sample_product_urls=(
            "https://www.nykaa.com/REPLACE-skincare-1",
            "https://www.nykaa.com/REPLACE-skincare-2",
            "https://www.nykaa.com/REPLACE-skincare-3",
            "https://www.nykaa.com/REPLACE-haircare-1",
            "https://www.nykaa.com/REPLACE-haircare-2",
            "https://www.nykaa.com/REPLACE-haircare-3",
            "https://www.nykaa.com/REPLACE-bodycare-1",
            "https://www.nykaa.com/REPLACE-bodycare-2",
        ),
        needs_proxy=True,
        image_priority=2, catalog_priority=2,
    ),
    Retailer(
        slug="amazon_in", name="Amazon.in", tier=RetailerTier.MARKETPLACE,
        base_url="https://www.amazon.in",
        sample_product_urls=(
            "https://www.amazon.in/dp/REPLACE1",
            "https://www.amazon.in/dp/REPLACE2",
            "https://www.amazon.in/dp/REPLACE3",
            "https://www.amazon.in/dp/REPLACE4",
            "https://www.amazon.in/dp/REPLACE5",
            "https://www.amazon.in/dp/REPLACE6",
            "https://www.amazon.in/dp/REPLACE7",
            "https://www.amazon.in/dp/REPLACE8",
        ),
        needs_proxy=True,
        image_priority=5, catalog_priority=99, can_create_canonical=False,
    ),
    Retailer(
        slug="tira", name="Tira", tier=RetailerTier.MARKETPLACE,
        base_url="https://www.tirabeauty.com",
        sample_product_urls=tuple(f"https://www.tirabeauty.com/product/REPLACE{i}" for i in range(8)),
        needs_proxy=True,
        image_priority=3, catalog_priority=3,
    ),
    Retailer(
        slug="purplle", name="Purplle", tier=RetailerTier.MARKETPLACE,
        base_url="https://www.purplle.com",
        sample_product_urls=tuple(f"https://www.purplle.com/product/REPLACE{i}" for i in range(8)),
        needs_proxy=True,
        image_priority=4, catalog_priority=3,
    ),
)


_BY_SLUG = {r.slug: r for r in RETAILERS}


def retailer_by_slug(slug: str) -> Retailer:
    return _BY_SLUG[slug]
