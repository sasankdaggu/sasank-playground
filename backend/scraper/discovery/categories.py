"""Face skincare discovery categories — single source of truth for what to crawl.

To add a new category: append a DiscoveryCategory to ALL_CATEGORIES.
To add a new vertical (body, hair): create a new tuple and add to ALL_CATEGORIES.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveryCategory:
    retailer_slug: str
    hint: str               # stored in url_queue.category_hint, maps to product category_hint
    url: str                # category listing page, page 1 (pagination param added by crawler)
    pagination_param: str = "page"
    max_pages: int = 20


FACE_SKINCARE: tuple[DiscoveryCategory, ...] = (
    # ── Nykaa ──────────────────────────────────────────────────────────────────
    # Pagination: ?page_no=N (1-indexed)
    DiscoveryCategory("nykaa", "face_wash",   "https://www.nykaa.com/skin/face-wash-cleansers/c/38",    pagination_param="page_no"),
    DiscoveryCategory("nykaa", "moisturizer", "https://www.nykaa.com/skin/moisturisers/c/47",            pagination_param="page_no"),
    DiscoveryCategory("nykaa", "serum",       "https://www.nykaa.com/skin/serums-and-treatments/c/307",  pagination_param="page_no"),
    DiscoveryCategory("nykaa", "sunscreen",   "https://www.nykaa.com/skin/sun-care/c/54",                pagination_param="page_no"),
    DiscoveryCategory("nykaa", "toner",       "https://www.nykaa.com/skin/toner-mist/c/49",              pagination_param="page_no"),
    DiscoveryCategory("nykaa", "eye_care",    "https://www.nykaa.com/skin/eye-care/c/51",                pagination_param="page_no"),
    DiscoveryCategory("nykaa", "face_mask",   "https://www.nykaa.com/skin/face-masks/c/53",              pagination_param="page_no"),
    # ── Tira (Fynd platform) ───────────────────────────────────────────────────
    # Pagination: ?page=N
    DiscoveryCategory("tira",  "face_care",   "https://www.tirabeauty.com/c/face-care-21454"),
    DiscoveryCategory("tira",  "serum",       "https://www.tirabeauty.com/c/face-serum-21463"),
    DiscoveryCategory("tira",  "moisturizer", "https://www.tirabeauty.com/c/moisturiser-21461"),
    DiscoveryCategory("tira",  "sunscreen",   "https://www.tirabeauty.com/c/sunscreen-21458"),
    DiscoveryCategory("tira",  "face_wash",   "https://www.tirabeauty.com/c/face-wash-cleanser-21456"),
    # ── Purplle ────────────────────────────────────────────────────────────────
    # Pagination: ?page=N
    DiscoveryCategory("purplle", "face_wash",   "https://www.purplle.com/face-wash/all"),
    DiscoveryCategory("purplle", "moisturizer", "https://www.purplle.com/moisturizer/all"),
    DiscoveryCategory("purplle", "serum",       "https://www.purplle.com/face-serum/all"),
    DiscoveryCategory("purplle", "sunscreen",   "https://www.purplle.com/sunscreen/all"),
    DiscoveryCategory("purplle", "toner",       "https://www.purplle.com/toner-mist/all"),
    DiscoveryCategory("purplle", "face_mask",   "https://www.purplle.com/face-mask/all"),
    DiscoveryCategory("purplle", "eye_care",    "https://www.purplle.com/eye-care/all"),
)

# Extend here when adding body care, hair care, etc.
ALL_CATEGORIES: tuple[DiscoveryCategory, ...] = FACE_SKINCARE
