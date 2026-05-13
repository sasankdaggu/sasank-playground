"""Retailer definitions — single source of truth for scraper and DB seeding."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RetailerTier(str, Enum):
    SHOPIFY = "shopify"
    MARKETPLACE = "marketplace"
    CUSTOM = "custom"  # Non-Shopify D2C brands scraped via sitemap + HTML parsing


@dataclass(frozen=True)
class Retailer:
    slug: str
    name: str
    tier: RetailerTier
    base_url: str
    products_json_url: str | None = None
    # When set, scraper uses /collections/{handle}/products.json instead of /products.json
    # to match storefront-visible catalog (excludes gifts, free samples, bundles)
    collection_handle: str | None = None
    sample_product_urls: tuple[str, ...] = field(default_factory=tuple)
    needs_proxy: bool = False
    # Lower number = higher quality source. D2C brand sites win over marketplaces.
    image_priority: int = 99
    # Whether this retailer can create a new canonical product row.
    can_create_canonical: bool = True
    # 1=always authoritative, 2=fallback if no D2C, 3=last resort, 99=never
    catalog_priority: int = 99
    is_authoritative_for_catalog: bool = False
    # CUSTOM tier: sitemap URL and URL substring that identifies product pages
    sitemap_url: str | None = None
    product_url_pattern: str | None = None
    # Substrings that disqualify a URL even if it matches product_url_pattern
    exclude_url_patterns: tuple[str, ...] = field(default_factory=tuple)
    # Minimum number of non-empty path segments required (0 = no filter).
    # Useful when a sitemap mixes category pages and product pages at different depths.
    min_path_depth: int = 0
    # CUSTOM tier: use Playwright instead of httpx (for sites needing JS rendering)
    needs_playwright: bool = False
    # CUSTOM tier: category page URLs to crawl via Playwright for product links
    # (used when product URLs are not in a sitemap, e.g. Magento 2 stores)
    catalog_pages: tuple[str, ...] = field(default_factory=tuple)
    # CUSTOM tier: regex (with one capture group) to extract product URL paths from
    # catalog pages via httpx — used when Playwright isn't needed and product URLs
    # aren't in the sitemap (e.g. Next.js stores like Olay India)
    catalog_link_regex: str | None = None


def _d2c(slug: str, name: str, base_url: str, collection_handle: str | None = None) -> Retailer:
    """Convenience constructor for D2C Shopify brands."""
    return Retailer(
        slug=slug, name=name, tier=RetailerTier.SHOPIFY,
        base_url=base_url,
        products_json_url=f"{base_url}/products.json",
        collection_handle=collection_handle,
        image_priority=1, catalog_priority=1, is_authoritative_for_catalog=True,
    )


def _custom(
    slug: str, name: str, base_url: str,
    sitemap_url: str, product_url_pattern: str,
    exclude_url_patterns: tuple[str, ...] = (),
) -> Retailer:
    """Convenience constructor for non-Shopify D2C brands scraped via sitemap."""
    return Retailer(
        slug=slug, name=name, tier=RetailerTier.CUSTOM,
        base_url=base_url,
        sitemap_url=sitemap_url,
        product_url_pattern=product_url_pattern,
        exclude_url_patterns=exclude_url_patterns,
        image_priority=1, catalog_priority=1, is_authoritative_for_catalog=True,
    )


RETAILERS: tuple[Retailer, ...] = (
    # ── Original D2C brands ────────────────────────────────────────────────────
    _d2c("minimalist",    "Minimalist",    "https://beminimalist.co",    "all-products"),
    _d2c("plum",          "Plum Goodness", "https://plumgoodness.com",   "all"),
    _d2c("mcaffeine",     "mCaffeine",     "https://mcaffeine.com",      "all"),
    _d2c("dot_and_key",   "Dot & Key",     "https://dotandkey.com",      "shop-all"),
    _d2c("the_derma_co",  "The Derma Co",  "https://thedermaco.com",     "all"),

    # ── Newly added D2C brands (from active ingredient strategies) ─────────────
    _d2c("82e",               "82°E",                    "https://82e.com",              "all"),
    _d2c("aqualogica",        "Aqualogica",              "https://aqualogica.in",        "all"),
    _d2c("bare_necessities",  "Bare Necessities",        "https://barenecessities.in",   "all"),
    _d2c("beauty_by_boe",     "Beauty by Boe",           "https://beautybybie.com",      "all"),
    _d2c("beauty_of_joseon",  "Beauty of Joseon",        "https://beautyofjoseon.com",   "all"),
    _d2c("brillare",          "Brillare",                "https://brillare.co.in",       "all"),
    _d2c("clayco",            "Clay Co",                 "https://clayco.in",            "all"),
    _d2c("conscious_chemist", "Conscious Chemist",       "https://consciouschemist.com", "all"),
    _d2c("daughter_earth",    "Daughter Earth",          "https://daughter.earth",       "all"),
    _d2c("dermalogica_in",    "Dermalogica India",       "https://dermalogica.in",       "all"),
    _d2c("deyga",             "Deyga",                   "https://deyga.in",             "all"),
    _d2c("pilgrim",           "Pilgrim",                 "https://discoverpilgrim.com",  "all"),
    _d2c("dr_sheths",         "Dr. Sheth's",             "https://drsheths.com",         "all"),
    _d2c("dyou",              "D'you",                   "https://dyou.co",              "all"),
    _d2c("earth_rhythm",      "Earth Rhythm",            "https://earthrhythm.com",      "all"),
    _d2c("fae_beauty",        "FAE Beauty",              "https://faebeauty.in",         "all"),
    _d2c("foxtale",           "Foxtale",                 "https://foxtale.in",           "all"),
    _d2c("hibiscus_monkey",   "Hibiscus Monkey",         "https://hibiscusmonkey.com",   "all"),
    _d2c("innisfree_in",      "Innisfree India",         "https://in.innisfree.com",     "all"),
    _d2c("indewild",          "Indewild",                "https://india.indewild.com",   "all"),
    _d2c("pixi_in",           "Pixi Beauty India",       "https://in.pixibeauty.com",    "all"),
    _d2c("pure_earth",        "Pure Earth",              "https://india.purearth.asia",  "all"),
    _d2c("innovist",          "Innovist",                "https://innovist.com",         "all"),
    _d2c("juicy_chemistry",   "Juicy Chemistry",         "https://juicychemistry.com",   "all"),
    _d2c("kiehls_in",         "Kiehl's India",           "https://kiehls.in",            "all"),
    _d2c("lets_hyphen",       "Let's Hyphen",            "https://letshyphen.com",       "all"),
    _d2c("embryolisse",       "Embryolisse",             "https://myembryolisse.com",    "all"),
    _d2c("world_of_asaya",    "World of Asaya",          "https://worldofasaya.com",     "all"),
    _d2c("paulas_choice_in",  "Paula's Choice India",    "https://paulaschoice.in",      "all"),
    _d2c("putsimply",         "Putsimply",               "https://putsimply.co.in",      "all"),
    _d2c("quench_botanics",   "Quench Botanics",         "https://quenchbotanics.com",   "all"),
    _d2c("raise_beauty",      "Raise Beauty",            "https://raisebeauty.com",      "all"),
    _d2c("reequil",           "Re'equil",                "https://reequil.com",          "all"),
    _d2c("simple_in",         "Simple India",            "https://simpleskincare.in",    "all"),
    _d2c("suhi_and_sego",     "Suhi & Sego",             "https://suhiandsego.com",      "all"),
    _d2c("the_dearist",       "The Dearist",             "https://thedearist.com",       "all"),
    _d2c("the_deconstruct",   "The Deconstruct",         "https://thedeconstruct.in",    "all"),
    _d2c("the_face_shop_in",  "The Face Shop India",     "https://thefaceshop.in",       "all"),
    _d2c("the_formula_rx",    "The Formula Rx",          "https://theformularx.com",     "all"),
    _d2c("the_pink_foundry",  "The Pink Foundry",        "https://thepinkfoundry.com",   "all"),
    _d2c("lakme",             "Lakmé India",             "https://www.lakmeindia.com",   "face"),
    _d2c("fixderma",          "Fixderma",                "https://www.fixderma.com",     "all"),
    _d2c("brwn",              "BRWN",                    "https://brwn.in",              "all"),
    _d2c("dabtofab",          "Dab to Fab",              "https://dabtofab.co",          "all"),
    _d2c("beyond_beyond",     "Beyond Beyond",           "https://beyondbeyond.co.in",   "all"),
    _d2c("lotus",             "Lotus Herbals",           "https://www.lotus.in",         "all"),
    _d2c("ponds_in",          "Pond's India",            "https://ponds.in",             "all"),
    _d2c("himalaya",          "Himalaya Wellness",       "https://himalayawellness.in",  "all"),

    # ── Custom (non-Shopify) D2C brands — sitemap-based catalog scraping ──────
    Retailer(
        slug="forest_essentials", name="Forest Essentials", tier=RetailerTier.CUSTOM,
        base_url="https://www.forestessentialsindia.com",
        # No sitemap with product URLs — uses Playwright category crawler instead
        catalog_pages=(
            "https://www.forestessentialsindia.com/facial-care/all-products.html",
        ),
        image_priority=1, catalog_priority=1, is_authoritative_for_catalog=True,
    ),
    _custom("kama_ayurveda",  "Kama Ayurveda",       "https://www.kamaayurveda.in",
            sitemap_url="https://www.kamaayurveda.in/media/sitemap/products.xml",
            product_url_pattern=".html",
            exclude_url_patterns=("/wellness/by-category", "/shop.html", "/best-seller.html")),
    _custom("cetaphil_in",    "Cetaphil India",      "https://www.cetaphil.in",
            sitemap_url="https://www.cetaphil.in/sitemap_0-product.xml",
            product_url_pattern="/product",
            exclude_url_patterns=()),
    _custom("neutrogena_in",  "Neutrogena India",    "https://www.neutrogena.in",
            sitemap_url="https://www.neutrogena.in/sitemap.xml",
            product_url_pattern="/face/",
            exclude_url_patterns=("/body/", "/sun/", "/hair/", "/baby/")),
    _custom("mamaearth",    "Mamaearth",          "https://mamaearth.in",
            sitemap_url="https://mamaearth.in/sitemap.xml",
            product_url_pattern="/product/",
            exclude_url_patterns=("/reviews", "/questions", "/compare")),
    _custom("nathabit",     "Nathabit",            "https://nathabit.in",
            sitemap_url="https://nathabit.in/sitemap.xml",
            product_url_pattern="/products/",
            exclude_url_patterns=("/collections/",)),
    Retailer(
        slug="be_bodywise", name="Be Bodywise", tier=RetailerTier.CUSTOM,
        base_url="https://bebodywise.com",
        sitemap_url="https://bebodywise.com/sitemap-products.xml",
        product_url_pattern="/product/",
        exclude_url_patterns=("/reviews", "/questions"),
        needs_playwright=True,
        image_priority=1, catalog_priority=1, is_authoritative_for_catalog=True,
    ),
    _custom("plix",         "Plix",                "https://www.plixlife.com",
            sitemap_url="https://www.plixlife.com/sitemap-products.xml",
            product_url_pattern="/product/",
            exclude_url_patterns=()),
    Retailer(
        slug="thebodyshop_in", name="The Body Shop India", tier=RetailerTier.CUSTOM,
        base_url="https://www.thebodyshop.in",
        sitemap_url="https://www.thebodyshop.in/sitemap/sitemap-products.xml",
        product_url_pattern="/p/",
        exclude_url_patterns=("/p/tbscombo", "/c/"),
        needs_proxy=True,
        image_priority=1, catalog_priority=1, is_authoritative_for_catalog=True,
    ),
    # Olay India: Next.js site, no product URLs in sitemap — extract slugs from 12 category pages
    Retailer(
        slug="olay_in", name="Olay India", tier=RetailerTier.CUSTOM,
        base_url="https://www.olayskincare.com",
        catalog_pages=(
            "https://www.olayskincare.com/en-in/skin-care-products/serums/",
            "https://www.olayskincare.com/en-in/skin-care-products/dry-skin/",
            "https://www.olayskincare.com/en-in/skin-care-products/eye-care/",
            "https://www.olayskincare.com/en-in/skin-care-products/cleansers/",
            "https://www.olayskincare.com/en-in/skin-care-products/vitamin-c/",
            "https://www.olayskincare.com/en-in/skin-care-products/anti-aging/",
            "https://www.olayskincare.com/en-in/skin-care-products/facial-moisturisers/",
            "https://www.olayskincare.com/en-in/skin-care-products/brightening-creams/",
            "https://www.olayskincare.com/en-in/skin-care-products/oily-skin-and-pores/",
            "https://www.olayskincare.com/en-in/skin-care-products/sun-protection-uv/",
            "https://www.olayskincare.com/en-in/skin-care-products/fine-lines-wrinkles/",
            "https://www.olayskincare.com/en-in/skin-care-products/retinol-24/",
        ),
        # Matches product paths only (olay- prefix or retinol prefix, not category slugs)
        catalog_link_regex=r'(/en-in/skin-care-products/(?:olay-|retinol)[a-z0-9][a-z0-9\-]*/)',
        image_priority=1, catalog_priority=1, is_authoritative_for_catalog=True,
    ),
    Retailer(
        slug="cerave_in", name="CeraVe India", tier=RetailerTier.CUSTOM,
        base_url="https://www.ceraveindia.com",
        sitemap_url="https://www.ceraveindia.com/sitemap.xml",
        product_url_pattern="/ceramides-skin-care/",
        # Sitemap mixes 2-segment category pages with 3-segment product pages;
        # require depth ≥ 3 to skip categories
        min_path_depth=3,
        image_priority=1, catalog_priority=1, is_authoritative_for_catalog=True,
    ),
    Retailer(
        slug="bioderma_in", name="Bioderma India", tier=RetailerTier.CUSTOM,
        base_url="https://www.bioderma-india.in",
        sitemap_url="https://www.bioderma-india.in/sitemap.xml",
        product_url_pattern="/our-products/",
        # Sitemap has mixed 1-segment category pages (/our-products/face) and
        # 2-segment product pages (/our-products/sensibio/h2o); require depth ≥ 2
        min_path_depth=2,
        image_priority=1, catalog_priority=1, is_authoritative_for_catalog=True,
    ),

    # ── Marketplaces (Tier 1) — pricing + cross-listing only ──────────────────
    Retailer(
        slug="nykaa", name="Nykaa", tier=RetailerTier.MARKETPLACE,
        base_url="https://www.nykaa.com",
        needs_proxy=True, image_priority=2, catalog_priority=2,
    ),
    Retailer(
        slug="tira", name="Tira", tier=RetailerTier.MARKETPLACE,
        base_url="https://www.tirabeauty.com",
        needs_proxy=True, image_priority=3, catalog_priority=3,
    ),
    Retailer(
        slug="purplle", name="Purplle", tier=RetailerTier.MARKETPLACE,
        base_url="https://www.purplle.com",
        needs_proxy=True, image_priority=4, catalog_priority=3,
    ),
    Retailer(
        slug="amazon_in", name="Amazon.in", tier=RetailerTier.MARKETPLACE,
        base_url="https://www.amazon.in",
        needs_proxy=True, image_priority=5, catalog_priority=99,
        can_create_canonical=False,
    ),
)

_BY_SLUG: dict[str, Retailer] = {r.slug: r for r in RETAILERS}


def retailer_by_slug(slug: str) -> Retailer:
    return _BY_SLUG[slug]
