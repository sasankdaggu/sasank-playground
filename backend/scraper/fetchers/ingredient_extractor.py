"""Per-brand ingredient extraction from D2C product pages.

Uses CSS selectors stored in scraping.ingredient_strategies to extract INCI ingredient lists.
All brand-specific logic lives in the DB strategy; there are no hardcoded extractors here.

mCaffeine is handled via a DB strategy with status='no_inci' — callers receive None.

Two execution paths:
  - requires_js=False: plain httpx fetch (fast, no proxy needed for D2C brands)
  - requires_js=True: Playwright with scroll + optional accordion click (triggers lazy-loaded
    sections and JS-populated elements like Dot & Key's opend-full-ingredients)
"""
from __future__ import annotations

import asyncio
import html as html_module
import re

import httpx
import structlog

log = structlog.get_logger()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    # Cloudflare bot-management bypass — these sec-fetch-* headers make httpx requests
    # indistinguishable from real browser navigation for brands like Pixi, Quench, Innisfree.
    "Cache-Control": "no-cache",
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-dest": "document",
}

_MAX_RETRIES = 3

# Tried in order — clicks the first visible element to expand ingredient accordions.
# summary selectors are safe (native HTML toggle, won't navigate). Class-based accordion
# and tab triggers are included for brands like Neutrogena/The Face Shop/Hibiscus Monkey.
_INGREDIENT_CLICK_SELECTORS = (
    'summary:has-text("INGREDIENT")',
    'summary:has-text("Full Ingredient")',  # Brillare "Full Ingredients" — more specific than "Ingredient"
    'summary:has-text("Ingredient")',
    '[class*="accordion"]:has-text("Ingredients")',
    '[class*="accordion-title"]:has-text("Ingredient")',
    '[class*="tab"]:has-text("INGREDIENT")',
    '[class*="tab"]:has-text("Ingredient")',
)

# Domains that block headless browsers at CDN level — require ScraperAPI proxy.
_CDN_BLOCKED_DOMAINS = frozenset({
    "neutrogena.in",
    "aveeno.in",
})


async def fetch_ingredient_text(
    url: str,
    retailer_slug: str,
    strategy: dict | None = None,
) -> str | None:
    """Fetch a D2C product page and extract the INCI ingredient list.

    Args:
        url: product page URL
        retailer_slug: used for logging only
        strategy: dict from scraping.ingredient_strategies row
                  (keys: css_selector, requires_js, status)

    Returns the raw INCI text string, or None if not found / not available.
    """
    if not strategy:
        log.warning("no_strategy_for_retailer", retailer=retailer_slug, url=url)
        return None

    if strategy.get("status") in ("no_inci", "failed"):
        return None

    css_selector = strategy.get("css_selector")
    if not css_selector:
        log.warning("strategy_has_no_selector", retailer=retailer_slug, status=strategy.get("status"))
        return None

    return await _extract_with_strategy(url, strategy)


async def _extract_with_strategy(url: str, strategy: dict) -> str | None:
    """Extract INCI using a DB-stored strategy (CSS selector or rsc: extractor)."""
    from urllib.parse import urlparse
    css_selector = strategy["css_selector"]
    requires_js = strategy.get("requires_js", False)
    domain = urlparse(url).netloc
    domain = domain[4:] if domain.startswith("www.") else domain
    use_proxy = domain in _CDN_BLOCKED_DOMAINS

    # rsc:<key> selectors extract from Next.js RSC JSON payload without Playwright
    if css_selector and css_selector.startswith("rsc:"):
        rsc_key = css_selector[4:]
        page_html = await _fetch_page_with_proxy(url) if use_proxy else await _fetch_page(url)
        if not page_html:
            return None
        return _extract_from_rsc(rsc_key, page_html)

    # nextdata: selectors extract from __NEXT_DATA__ JSON without Playwright
    if css_selector and css_selector.startswith("nextdata:"):
        page_html = await _fetch_page_with_proxy(url) if use_proxy else await _fetch_page(url)
        if not page_html:
            return None
        return _extract_from_next_data(page_html)

    # tablecol: selectors extract first-column <td> values from an HTML table and join with ", "
    # Format: tablecol:<container_selector>  e.g. tablecol:.ingredients-table-container
    if css_selector and css_selector.startswith("tablecol:"):
        container_sel = css_selector[9:]
        page_html = await _fetch_page(url)
        if not page_html:
            page_html = await _fetch_playwright(url)
        if not page_html:
            return None
        return _extract_table_first_col(container_sel, page_html)

    # faelink: fetches a shared ingredients page and matches the current product by URL slug
    # Format: faelink:<ingredients_page_url>  e.g. faelink:https://www.faebeauty.in/pages/ingredients-1
    if css_selector and css_selector.startswith("faelink:"):
        ingredients_page_url = css_selector[8:]
        ingredients_html = await _fetch_page(ingredients_page_url)
        if not ingredients_html:
            return None
        return _extract_from_faelink(url, ingredients_html)

    # mamaearthtable: extracts INCI from Mamaearth __NEXT_DATA__ cmsContent ingredient table
    if css_selector and css_selector.startswith("mamaearthtable:"):
        page_html = await _fetch_page(url)
        if not page_html:
            page_html = await _fetch_playwright(url)
        if not page_html:
            return None
        result = _extract_from_mamaearth_table(page_html)
        if result:
            return result
        # cmsContent is empty in SSR HTML for some products (showMetaPDP=True flag).
        # Fall back to fetching via the Next.js _next/data/ JSON API using variant url_keys
        # found in product.configurable_options — those pages have full cmsContent.
        return await _extract_mamaearth_variant_api(url, page_html)

    # itemlist:<container>##<item_selector> — extracts text from each matching item element,
    # strips child tags, and joins with ", ".  Used for Beyond Beyond ingredient tiles.
    if css_selector and css_selector.startswith("itemlist:"):
        spec = css_selector[9:]
        container_sel, item_sel = spec.split("##", 1) if "##" in spec else (None, spec)
        page_html = await _fetch_page(url)
        if not page_html:
            page_html = await _fetch_playwright(url)
        if not page_html:
            return None
        return _extract_item_list(container_sel, item_sel, page_html)

    # paulaschoice: extracts INCI from Paula's Choice India __NEXT_DATA__ or static HTML
    # Finds span.metafield-multi_line_text_field near <h2>INGREDIENTS</h2>, splits on "All Ingredients"
    if css_selector and css_selector.startswith("paulaschoice:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_paulaschoice(page_html)

    # tbsdata: extracts INCI from The Body Shop India __NEXT_DATA__
    # Navigates to customAttributes list and finds attribute_code == "ingredients"
    if css_selector and css_selector.startswith("tbsdata:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_bodyshop_data(page_html)

    # bojmodal: extracts INCI from Beauty of Joseon's ingredient modal popup.
    # The modal (product-modal__outer) renders after Playwright scroll; ingredient
    # text is a direct text node inside the modal, after the close button.
    if css_selector and css_selector.startswith("bojmodal:"):
        page_html = await _fetch_playwright(url)
        if not page_html:
            return None
        return _extract_boj_modal(page_html)

    # drsheths: extracts INCI from Dr. Sheth's rendered ingredient accordion.
    # INCI lives in span.detail2 inside the "Ingredients" hdt-accordion section,
    # which is JS-rendered. The brand blocks plain httpx with Cloudflare; Playwright bypasses it.
    if css_selector and css_selector.startswith("drsheths:"):
        page_html = await _fetch_playwright(url, use_proxy=use_proxy)
        if not page_html:
            return None
        return _extract_drsheths(page_html)

    # dearth: extracts INCI from Daughter Earth's Shogun page builder accordion.
    # Finds the shogun-accordion-body that follows the "Ingredients" accordion header
    # and strips all nested spans to return the plain INCI text.
    if css_selector and css_selector.startswith("dearth:"):
        page_html = await _fetch_playwright(url)
        if not page_html:
            return None
        return _extract_daughter_earth(page_html)

    # raisebeauty: extracts INCI from Raise Beauty's JSON-LD Product description.
    # Description is HTML-encoded; strip tags then find text after "Ingredients" heading.
    if css_selector and css_selector.startswith("raisebeauty:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_raisebeauty(page_html)

    # inciparagraph:<container> — finds the first INCI-like <p> inside the container;
    # falls back to the longest paragraph if none passes _looks_like_inci.
    # Used for brands (e.g. Suhi & Sego) where INCI is one paragraph among marketing copy.
    if css_selector and css_selector.startswith("inciparagraph:"):
        container_sel = css_selector[14:]
        page_html = await _fetch_page(url)
        if not page_html:
            page_html = await _fetch_playwright(url)
        if not page_html:
            return None
        return _extract_inci_paragraph(container_sel, page_html)

    # deyga: extracts INCI from Deyga's JSON-LD Product description field.
    # The ingredients-drawer-body is AJAX-loaded (always empty in static HTML).
    # INCI lives in JSON-LD description after "Ingredients\n" as a hyphen-prefixed list.
    if css_selector and css_selector.startswith("deyga:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_deyga(page_html)

    # dearist: extracts INCI from The Dearist's tab-content-1 section.
    # INCI is in the last <p> after "Full Ingredient List" heading; first <p> is marketing copy.
    if css_selector and css_selector.startswith("dearist:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_dearist(page_html)

    # quenchbotanics: extracts INCI from Quench Botanics product pages.
    # Two structures: (1) <p>Complete Ingredient List: ...</p> in metafield div,
    # (2) JSON-LD Product.description with "Complete ingredient list: ..." fallback.
    if css_selector and css_selector.startswith("quenchbotanics:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_quenchbotanics(page_html)

    # barenecessities: extracts INCI from Bare Necessities product pages.
    # INCI is a raw text node following <strong>Ingredients:</strong>, outside the tab UL.
    if css_selector and css_selector.startswith("barenecessities:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_barenecessities(page_html)

    # deconstruct: extracts INCI from The Deconstruct's accordion-tab:nth-of-type(3).
    # Tab 3 always contains "PRODUCT INGREDIENTS". The first <p> is a heading;
    # the INCI is in the next <p> that passes _looks_like_inci.
    if css_selector and css_selector.startswith("deconstruct:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_deconstruct(page_html)

    # kiehls: extracts INCI from Kiehl's .ingredients-popup-inner div.
    # The popup is in static HTML for most products; validate with _looks_like_inci to
    # avoid storing placeholder product names that also appear in the same div.
    if css_selector and css_selector.startswith("kiehls:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_kiehls(page_html)

    # embryolisse: #collapseTwo4 .card-body contains "Manufacturing Details" with
    # period-separated INCI after the manufacturer address (stripped on extraction).
    if css_selector and css_selector.startswith("embryolisse:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        m = re.search(
            r'id="collapseTwo4".*?<div[^>]*class="[^"]*card-body[^"]*"[^>]*>(.*?)</div\s*>',
            page_html, re.DOTALL | re.IGNORECASE,
        )
        if not m:
            return None
        raw = html_module.unescape(re.sub(r'<[^>]+>', ' ', m.group(1)))
        raw = re.sub(r'\s+', ' ', raw).strip()
        # Strip manufacturer address prefix (up to "France")
        addr_m = re.search(r'France\s*', raw, re.IGNORECASE)
        if addr_m:
            raw = raw[addr_m.end():].strip()
        # Convert period-separated INCI to comma-separated
        raw = re.sub(r'\.\s+', ', ', raw).rstrip('. ')
        return _clean_inci(raw) if len(raw) > 10 else None

    # biestyle: extracts INCI from BiE (Beauty by BoE) accordion-tab whose summary
    # contains "INGREDIENTS". Tab position varies, so we scan by summary text.
    if css_selector and css_selector.startswith("biestyle:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_biestyle(page_html)

    # earthrhythm: tries div[data-key="k3-content"] (legacy template) then
    # #ingredient-modal-sec .modal-inner-section (modal template used on oils/newer pages).
    # Oils use "(and)" separators instead of commas, so we bypass _looks_like_inci for the modal.
    if css_selector and css_selector.startswith("earthrhythm:"):
        from scraper.ingredient_schema_detector import validate_selector as _vs
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        result = _vs('div[data-key="k3-content"]', page_html)
        if not result:
            result = _vs('div.product-details__ingredient-text p', page_html)
        if not result:
            # Modal template: oils use "(and)" separators → direct regex, skip _looks_like_inci
            m = re.search(
                r'<div[^>]*class="[^"]*modal-inner-section[^"]*"[^>]*>(.*?)</div\s*>',
                page_html, re.DOTALL | re.IGNORECASE,
            )
            if m:
                raw = html_module.unescape(re.sub(r'<[^>]+>', '', m.group(1)))
                raw = re.sub(r'\s+', ' ', raw).strip()
                if len(raw) > 10:
                    result = _clean_inci(raw)
        if not result:
            # Pure oil products store "Ingredient: X" in JSON-encoded product description
            jm = re.search(r'[Ii]ngredient\s*:\\u003c\\/strong\\u003e\s*(.*?)\\u003c', page_html)
            if jm:
                raw = jm.group(1).strip()
                if len(raw) > 5:
                    result = _clean_inci(raw)
        if not result:
            # Description template: <strong>Ingredients</strong> : <span>INCI list</span>
            from scraper.ingredient_schema_detector import _looks_like_inci
            sm = re.search(
                r'<strong>[Ii]ngredients?</strong>\s*:[\s\xa0]*<span[^>]*>(.*?)</span>',
                page_html, re.DOTALL | re.IGNORECASE,
            )
            if sm:
                raw = html_module.unescape(re.sub(r'<[^>]+>', '', sm.group(1)))
                raw = re.sub(r'\s+', ' ', raw).strip()
                if len(raw) > 20 and _looks_like_inci(raw):
                    result = _clean_inci(raw)
        return result

    # reequil: tries .accordion-details__content p (current template) then .allIgrdes (bundles).
    # Note: pack-of-2 pages use <div class="accordion-details"> not <details class="accordion-details">,
    # so the selector omits the element constraint to match both.
    if css_selector and css_selector.startswith("reequil:"):
        from scraper.ingredient_schema_detector import validate_selector as _vs
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        result = _vs(".accordion-details .accordion-details__content p", page_html)
        if not result:
            result = _vs(".allIgrdes", page_html)
        return result

    # clayco: extracts INCI from Clayco's INGREDIENTS accordion.
    # Page has multiple metafield-single_line_text_field-array sections (APPLICATION, INGREDIENTS);
    # find the one following <strong>INGREDIENTS</strong> and extract all <li> text.
    if css_selector and css_selector.startswith("clayco:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_clayco(page_html)

    # pixiin: extracts INCI from Pixi India (in.pixibeauty.com) product pages.
    # INCI lives in the "Ingredients" accordion section (.accordion-content-wrap-inner inside
    # the accordion-content-wrap whose sibling button contains "Ingredients").
    # The ingredients popup (.ingredients-popup__inner div.font-roboto) is always empty in
    # static HTML — the INCI is only in the accordion for individual products.
    # Bundles, kits, and brushes show feature bullets (not real INCI) in the same accordion;
    # we validate with _looks_like_inci to skip those.
    if css_selector and css_selector.startswith("pixiin:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_pixiin(page_html)

    if css_selector and css_selector.startswith("juicychemistry:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_juicychemistry(page_html)

    if css_selector and css_selector.startswith("brillare:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_brillare(page_html)

    # letshyphen: extracts INCI from Let's Hyphen Shopify pages.
    # The Shopify theme embeds product data as a JavaScript Products[] variable with
    # ##field: @@value## delimiters.  The INCI is after "##Ingredients: @@" and ends
    # at the next "##" field delimiter.
    if css_selector and css_selector.startswith("letshyphen:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_letshyphen(page_html)

    # dabtofab: extracts INCI from Dab to Fab (dabtofab.co) product pages.
    # INCI is in a <p> inside .accordion-content following an <h3> "Full Ingredients" heading.
    if css_selector and css_selector.startswith("dabtofab:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_dabtofab(page_html)

    # hibiscusmonkey: extracts INCI from Hibiscus Monkey product pages.
    # Each ingredient name is in <div class="pop-ingrd-accrdion-heading"><strong>Name</strong></div>
    # inside the modal ingredients table.  We collect all strong-text entries and join with ", ".
    if css_selector and css_selector.startswith("hibiscusmonkey:"):
        page_html = await _fetch_page(url)
        if not page_html:
            return None
        return _extract_hibiscusmonkey(page_html)

    if requires_js or use_proxy:
        page_html = await _fetch_playwright(url, use_proxy=use_proxy)
    else:
        page_html = await _fetch_page(url)
        if not page_html:
            # Static fetch failed — try Playwright as fallback
            page_html = await _fetch_playwright(url)

    if not page_html:
        return None

    raw = _apply_selector(css_selector, page_html)
    return _clean_inci(raw) if raw else None


def _apply_selector(selector: str, page_html: str) -> str | None:
    from scraper.ingredient_schema_detector import validate_selector
    return validate_selector(selector, page_html)


def _extract_from_rsc(key: str, page_html: str) -> str | None:
    """Extract content from Next.js RSC JSON payload via a Storyblok field-path key.

    The RSC payload embeds component data as double-escaped JSON in <script> tags.
    Key format matches data-sb-field-path values, e.g. 'drawer.body' finds:
      \"data-sb-field-path\":\".drawer.body\" ... \"__html\":\"\\u003cp\\u003eIngredients...\"
    """
    import html as html_module
    # Find the Storyblok field-path key in the RSC payload
    escaped_key = key.replace('.', r'\.')
    db_idx = page_html.find(key)
    if db_idx == -1:
        return None
    chunk = page_html[db_idx:db_idx + 1200]
    # Find __html value — contains \\uXXXX-encoded HTML
    start = chunk.find('\\u003cp')
    end = chunk.find('\\u003c/p\\u003e')
    if start == -1 or end == -1:
        return None
    encoded = chunk[start:end + len('\\u003c/p\\u003e')]
    # Decode literal \uXXXX sequences (backslash-u-4hex in the string)
    decoded = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), encoded)
    no_tags = re.sub(r'<[^>]+>', '', decoded)
    return _clean_inci(html_module.unescape(no_tags))


def _extract_from_next_data(page_html: str) -> str | None:
    """Extract INCI from Next.js __NEXT_DATA__ JSON by recursively searching 'body' keys.

    Walks all 'body' string values in the JSON tree and returns the first one
    that passes _looks_like_inci. Works for Olay India and similar Next.js sites
    where the full ingredient list is embedded under activeIngredients.body.
    """
    import json
    from scraper.ingredient_schema_detector import _looks_like_inci
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_html, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except Exception:
        return None

    def _search(obj: object) -> str | None:
        if isinstance(obj, dict):
            body = obj.get("body")
            if isinstance(body, str) and _looks_like_inci(body):
                return body
            for v in obj.values():
                found = _search(v)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = _search(item)
                if found:
                    return found
        return None

    result = _search(data)
    return _clean_inci(result) if result else None


_TABLE_HEADER_SKIP = frozenset(('ingredient', 'ingredients', 'name', 'inci name', 'inci', ''))


def _parse_table_col(table_html: str, col_idx: int = 0) -> list[str]:
    """Extract text from a specific column (0-indexed) of all non-header <td> rows."""
    rows = re.findall(r'<tr[^>]*>(.*?)</tr\s*>', table_html, re.DOTALL | re.IGNORECASE)
    result = []
    for row in rows:
        tds = re.findall(r'<td[^>]*>(.*?)</td\s*>', row, re.DOTALL | re.IGNORECASE)
        if len(tds) > col_idx:
            text = re.sub(r'<[^>]+>', '', tds[col_idx]).strip()
            text = re.sub(r'\s+', ' ', text).strip()
            if text.lower() not in _TABLE_HEADER_SKIP:
                result.append(text)
    return result


def _extract_table_first_col(container_selector: str, page_html: str) -> str | None:
    """Find the container element by selector, then extract first-column <td> text and join with ', '.

    Used for Pilgrim-style ingredient tables where the INCI is split across rows.
    """
    from scraper.ingredient_schema_detector import _selector_to_open_regex
    open_pat = _selector_to_open_regex(container_selector)
    if not open_pat:
        return None
    m = re.search(open_pat, page_html, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    chunk = page_html[m.start(): m.start() + 30_000]
    ingredients = _parse_table_col(chunk)
    if not ingredients:
        return None
    return _clean_inci(', '.join(ingredients))


def _extract_from_faelink(product_url: str, ingredients_html: str) -> str | None:
    """Extract FAE Beauty INCI by matching product slug in their shared ingredients page.

    The ingredients page (/pages/ingredients-1) has one <a href=".../{slug}"> per product.
    The INCI text follows each anchor tag's parent bold/italic wrapper until the next <a href=>.
    Tries all matching anchors to handle empty anchors and navigation-link false matches.
    """
    from urllib.parse import urlparse
    slug = urlparse(product_url).path.rstrip('/').split('/')[-1]
    # Build candidate slugs: exact slug first, then progressively strip size/variant suffixes
    # e.g. "spf-juice-100ml-bottle" → try "spf-juice" by removing -NNNml/-NNNg/-NNNgm patterns
    candidate_slugs = [slug]
    base = re.sub(r'-\d+(?:ml|g|gm|oz)[^-]*$', '', slug)
    if base and base != slug:
        candidate_slugs.append(base)
    base2 = re.sub(r'-(?:new|travel|mini|small|large|set|kit|[0-9]+).*$', '', slug, flags=re.IGNORECASE)
    if base2 and base2 != slug and base2 not in candidate_slugs:
        candidate_slugs.append(base2)

    for try_slug in candidate_slugs:
        for m in re.finditer(
            rf'<a[^>]+href="[^"]*/{re.escape(try_slug)}(?:/|")',
            ingredients_html,
            re.IGNORECASE,
        ):
            # Bound this product's content: from the <a> tag to the next <a href=> (next product)
            start = m.start()
            next_anchor = re.search(r'<a\s[^>]*href=', ingredients_html[start + 10:], re.IGNORECASE)
            end = (start + 10 + next_anchor.start()) if next_anchor else (start + 2500)
            end = min(end, start + 2500)

            chunk = ingredients_html[start:end]
            plain = re.sub(r'<[^>]+>', '', chunk)
            plain = html_module.unescape(plain)
            plain = re.sub(r'\s+', ' ', plain).strip()

            # Split off the product-name prefix; the INCI follows "Ingredients:" (or just ":")
            inci_m = re.search(r'[Ii]ngredients?\s*:?\s*(.+)', plain, re.DOTALL)
            if not inci_m:
                # Fallback for "Name: INCI" pattern (e.g. colon inside link text)
                colon_m = re.search(r'^[^:]+:\s*(.+)', plain, re.DOTALL)
                if not colon_m:
                    continue
                raw_inci = colon_m.group(1)
            else:
                raw_inci = inci_m.group(1)

            if len(raw_inci.strip()) > 20:
                return _clean_inci(raw_inci)

    return None


def _extract_from_mamaearth_table(page_html: str) -> str | None:
    """Extract INCI from Mamaearth's __NEXT_DATA__ ingredient table.

    Mamaearth stores INCI as an HTML <table> inside props.pageProps.cmsContent.
    The entry with "Ingredient List" in its title list contains the full ingredient table
    (columns: Ingredient | Type | Where It's From | How It Helps).
    """
    import json
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_html, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except Exception:
        return None

    cms = data.get("props", {}).get("pageProps", {}).get("cmsContent") or []
    # Match any title variant containing "ingredient" (e.g. "Ingredient List",
    # "List of Ingredients", "Ingredient List Baby lip balm") while requiring a
    # <table> in the content to exclude "Key Ingredients" marketing copy.
    inci_entry = next(
        (
            c for c in cms
            if any("ingredient" in str(t).lower() for t in (c.get("title") or []))
            and "<table" in (c.get("content") or "").lower()
        ),
        None,
    )
    if not inci_entry:
        return None
    inci_html = inci_entry.get("content", "") or ""
    if not inci_html:
        return None

    ingredients = _parse_table_col(inci_html)
    if not ingredients:
        return None
    return _clean_inci(', '.join(ingredients))


async def _extract_mamaearth_variant_api(url: str, page_html: str) -> str | None:
    """Fallback extractor for Mamaearth products where __NEXT_DATA__ has cmsContent: [].

    Some Mamaearth product pages are served with showMetaPDP=True, which causes the SSR
    to omit the cmsContent ingredient table (empty array).  The full cmsContent is available
    via the Next.js _next/data/ JSON API when called with a variant-level url_key (the long
    canonical slug stored in product.configurable_options[X][i].url_key).

    Strategy:
    1. Parse __NEXT_DATA__ from the already-fetched page HTML to get buildId and all variant
       url_keys from product.configurable_options.
    2. For each variant url_key, fetch /_next/data/{buildId}/product/{url_key}.json
    3. Look for a cmsContent entry whose title contains "ingredient" and whose content has a
       <table> (the ingredient table with columns Ingredient | Type | Where It's From | How It Helps).
    4. Extract first-column ingredient names, join with ", ".
    """
    import json
    from urllib.parse import urlparse

    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_html, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except Exception:
        return None

    build_id = data.get("buildId", "")
    if not build_id:
        return None

    product = data.get("props", {}).get("pageProps", {}).get("product") or {}
    configurable_options = product.get("configurable_options") or {}

    # Collect all variant url_keys across all option dimensions
    variant_url_keys: list[str] = []
    for variants in configurable_options.values():
        if not isinstance(variants, list):
            continue
        for variant in variants:
            uk = variant.get("url_key", "") if isinstance(variant, dict) else ""
            if uk and uk not in variant_url_keys:
                variant_url_keys.append(uk)

    if not variant_url_keys:
        log.debug("mamaearth_no_variant_url_keys", url=url)
        return None

    base = "https://mamaearth.in"
    for uk in variant_url_keys:
        api_url = f"{base}/_next/data/{build_id}/product/{uk}.json?slug={uk}"
        api_html = await _fetch_page(api_url)
        if not api_html:
            continue
        try:
            api_data = json.loads(api_html)
        except Exception:
            continue

        cms = api_data.get("pageProps", {}).get("cmsContent") or []
        inci_entry = next(
            (
                c for c in cms
                if any("ingredient" in str(t).lower() for t in (c.get("title") or []))
                and "<table" in (c.get("content") or "").lower()
            ),
            None,
        )
        if not inci_entry:
            continue
        inci_html = inci_entry.get("content", "") or ""
        if not inci_html:
            continue
        ingredients = _parse_table_col(inci_html)
        if ingredients:
            log.info("mamaearth_variant_api_success", url=url, variant_slug=uk, count=len(ingredients))
            return _clean_inci(", ".join(ingredients))

    log.debug("mamaearth_variant_api_no_result", url=url, tried=len(variant_url_keys))
    return None


def _extract_item_list(container_selector: str | None, item_selector: str, page_html: str) -> str | None:
    """Extract direct text content from each matching item element and join with ', '.

    Used for Beyond Beyond ingredient tiles: each div.item_d has the ingredient name
    as a raw text node followed by a child <span.ingreInfo> tooltip — we take only
    the text before the first child tag.
    """
    from scraper.ingredient_schema_detector import _selector_to_open_regex
    search_html = page_html
    if container_selector:
        open_pat = _selector_to_open_regex(container_selector)
        if open_pat:
            m = re.search(open_pat, page_html, re.DOTALL | re.IGNORECASE)
            if m:
                search_html = page_html[m.start(): m.start() + 20_000]

    item_open_pat = _selector_to_open_regex(item_selector)
    if not item_open_pat:
        return None
    tag_m = re.match(r'^(\w[\w-]*)', item_selector)
    item_tag = re.escape(tag_m.group(1)) if tag_m else r'\w+'

    ingredients = []
    for m in re.finditer(item_open_pat, search_html, re.DOTALL | re.IGNORECASE):
        end_m = re.search(rf'</{item_tag}\s*>', search_html[m.end():], re.IGNORECASE)
        if not end_m:
            continue
        inner = search_html[m.end(): m.end() + end_m.start()]
        # Ingredient name is the direct text node before any child tag
        text = inner.split('<')[0] if '<' in inner else inner
        text = html_module.unescape(text).strip()
        text = re.sub(r'\s+', ' ', text).strip()
        if text and text.lower() not in _TABLE_HEADER_SKIP:
            ingredients.append(text)

    if not ingredients:
        return None
    return _clean_inci(', '.join(ingredients))


def _extract_paulaschoice(page_html: str) -> str | None:
    """Extract INCI from Paula's Choice India product pages.

    The full INCI is in span.metafield-multi_line_text_field inside the section that
    contains <h2>INGREDIENTS</h2>. Anchoring on the h2 heading avoids picking up the
    adjacent FAQ jsc-readMore div which also uses span.metafield-multi_line_text_field.
    The span has two sections: 'Key Ingredients' and 'All Ingredients' — we split and
    keep only the second half. Strips \u2060 (WORD JOINER) chars injected per ingredient.
    """
    # Match exact uppercase <h2>INGREDIENTS</h2> — case-sensitive to skip nav dropdowns
    # that also use <h2 class="...">Ingredients</h2>
    h2_m = re.search(r'<h2>\s*INGREDIENTS\s*</h2>', page_html)
    if not h2_m:
        return None
    # Find the metafield span opening tag after the h2 heading
    chunk = page_html[h2_m.start(): h2_m.start() + 5_000]
    span_m = re.search(
        r'<span[^>]*class="[^"]*metafield-multi_line_text_field[^"]*"[^>]*>',
        chunk, re.IGNORECASE,
    )
    if not span_m:
        return None
    # Extract from span content start onwards (strip HTML, don't need to find closing tag)
    after_open = chunk[span_m.end():]
    text = re.sub(r'<[^>]+>', ' ', after_open)
    text = html_module.unescape(text)
    text = re.sub(r'[\u2060\u200b\u200c\u200d\ufeff]', '', text)
    if 'All Ingredients' in text:
        text = text.split('All Ingredients', 1)[1]
    return _clean_inci(text[:1500])


def _extract_bodyshop_data(page_html: str) -> str | None:
    """Extract INCI from The Body Shop India __NEXT_DATA__ JSON.

    TBS India uses Next.js + Redux. The INCI is in:
      props.pageProps.initialState.productDetailReducer.product.customAttributes
    Find the item with attribute_code == 'ingredients' and decode its value field
    (stored as \\u003cp\\u003e-encoded HTML in the raw JSON).
    """
    import json
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_html, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except Exception:
        return None

    product = (
        data.get("props", {})
        .get("pageProps", {})
        .get("initialState", {})
        .get("productDetailReducer", {})
        .get("product", {})
    )
    if isinstance(product, list):
        product = product[0] if product else {}
    if not isinstance(product, dict):
        return None
    attrs = product.get("customAttributes") or []
    for attr in attrs:
        if attr.get("attribute_code") == "ingredients":
            value = attr.get("value", "") or ""
            if not value:
                continue
            no_tags = re.sub(r'<[^>]+>', '', value)
            return _clean_inci(html_module.unescape(no_tags))
    return None


async def _fetch_page(url: str) -> str:
    # Percent-encode non-ASCII characters (e.g. emoji in slugs) so httpx sends a valid URL
    try:
        url = url.encode("ascii").decode("ascii")
    except UnicodeEncodeError:
        from urllib.parse import quote
        url = quote(url, safe=":/?=&#%@!$&'()*+,;[]")
    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url)
            if resp.status_code == 404:
                log.warning("ingredient_page_404", url=url)
                return ""
            if resp.status_code == 429:
                wait = 20 * (attempt + 1)
                log.warning("ingredient_page_ratelimit", url=url, attempt=attempt, wait_s=wait)
                if attempt == _MAX_RETRIES - 1:
                    return ""
                await asyncio.sleep(wait)
                continue
            if resp.status_code >= 400:
                log.warning("ingredient_page_error", url=url, status=resp.status_code)
                if attempt == _MAX_RETRIES - 1:
                    return ""
                await asyncio.sleep(5 * (attempt + 1))
                continue
            await asyncio.sleep(0.5)  # polite pacing — 2 req/s max per worker
            return resp.text
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            if attempt == _MAX_RETRIES - 1:
                log.warning("ingredient_fetch_failed", url=url, error=str(exc))
                return ""
            await asyncio.sleep(5 * (attempt + 1))
    return ""


async def _fetch_page_with_proxy(url: str) -> str:
    """Plain httpx fetch routed through ScraperAPI proxy (no JS rendering)."""
    from app.config import settings
    proxy_url = f"http://scraperapi:{settings.scraperapi_key}@proxy-server.scraperapi.com:8001"
    transport = httpx.AsyncHTTPTransport(proxy=proxy_url, verify=False)
    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(
                transport=transport, headers=_HEADERS, timeout=45.0, follow_redirects=True
            ) as client:
                resp = await client.get(url)
            if resp.status_code == 404:
                return ""
            if resp.status_code >= 400:
                if attempt == _MAX_RETRIES - 1:
                    log.warning("proxy_fetch_error", url=url, status=resp.status_code)
                    return ""
                await asyncio.sleep(5 * (attempt + 1))
                continue
            return resp.text
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            if attempt == _MAX_RETRIES - 1:
                log.warning("proxy_fetch_failed", url=url, error=str(exc))
                return ""
            await asyncio.sleep(5 * (attempt + 1))
    return ""


async def _fetch_playwright(url: str, use_proxy: bool = False) -> str:
    """Fetch via Playwright: scroll to trigger lazy-loaded content, then try clicking
    ingredient accordion summaries (e.g. Dot & Key details/summary pattern).

    use_proxy=True routes through ScraperAPI for CDN-blocked domains.
    """
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth
        proxy = None
        if use_proxy:
            from app.config import settings
            proxy = {
                "server": "http://proxy-server.scraperapi.com:8001",
                "username": "scraperapi",
                "password": settings.scraperapi_key,
            }
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, proxy=proxy)
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=_HEADERS["User-Agent"],
                locale="en-IN",
                ignore_https_errors=bool(proxy),
            )
            page = await ctx.new_page()
            await Stealth().apply_stealth_async(page)
            try:
                timeout_ms = 90_000 if use_proxy else 45_000
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(3_000)
                # Scroll to trigger IntersectionObserver lazy-loaded sections
                await page.evaluate('window.scrollTo(0, 3000)')
                await page.wait_for_timeout(1_500)
                await page.evaluate('window.scrollTo(0, 6000)')
                await page.wait_for_timeout(1_500)
                # Try clicking ingredient accordion triggers (e.g. D&K INGREDIENTS summary)
                for sel in _INGREDIENT_CLICK_SELECTORS:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=1_000):
                            tag = await el.evaluate('el => el.tagName.toLowerCase()')
                            if tag == 'a':
                                href = await el.evaluate('el => el.getAttribute("href") || ""')
                                if href and not href.startswith('#'):
                                    continue
                            await el.scroll_into_view_if_needed()
                            await el.click()
                            await page.wait_for_timeout(2_000)
                            break
                    except Exception:
                        continue
                html_content = await page.content()
            finally:
                await page.close()
            await browser.close()
            return html_content
    except Exception as exc:
        log.warning("playwright_ingredient_fetch_failed", url=url, error=str(exc))
        return ""


def _extract_boj_modal(page_html: str) -> str | None:
    """Extract INCI from Beauty of Joseon's ingredient modal popup.

    The rendered page (post-Playwright) contains a product-modal__outer element.
    Its product-modal__content div has a close button followed by the INCI list.

    Sunscreen products use <br> tags to separate ingredients (not commas).
    We replace <br> with ", " before stripping all other tags so ingredients
    don't concatenate. ACTIVE/INACTIVE INGREDIENT headers are cleaned up.
    """
    m = re.search(r'<div class="product-modal__outer">(.*?)</dialog>', page_html, re.DOTALL)
    if not m:
        return None
    content = m.group(1)
    # Remove close button
    no_button = re.sub(r'<button[^>]*>.*?</button>', '', content, flags=re.DOTALL)
    # Replace <br> tags with ", " before stripping — these ARE ingredient separators
    no_br = re.sub(r'<br\s*/?>', ', ', no_button, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', no_br)
    text = html_module.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove ACTIVE INGREDIENT(S): and INACTIVE INGREDIENTS: headers (sunscreen format)
    text = re.sub(r'\bACTIVE\s+INGREDIENT[S]?\s*:,?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bINACTIVE\s+INGREDIENT[S]?\s*:,?\s*', '', text, flags=re.IGNORECASE)
    # Clean up stray double commas left by header removal
    text = re.sub(r',\s*,', ', ', text)
    text = text.strip().strip(',').strip()
    return _clean_inci(text) if len(text) > 20 else None


def _extract_drsheths(page_html: str) -> str | None:
    """Extract INCI from Dr. Sheth's rendered ingredient accordion.

    The INCI lives in span.detail2 inside the "Ingredients" hdt-accordion section,
    which only renders via Playwright. Kits have no "Ingredients" accordion, returning None.
    """
    # Find the <summary> element with text "Ingredients"
    for m in re.finditer(r'<summary[^>]*>(.*?)</summary\s*>', page_html, re.DOTALL | re.IGNORECASE):
        label = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if label.lower() == 'ingredients':
            # Look for span.detail2 in the next 3000 chars
            after = page_html[m.end(): m.end() + 3_000]
            d2 = re.search(
                r'<span[^>]*class="[^"]*\bdetail2\b[^"]*"[^>]*>(.*?)</span\s*>',
                after, re.DOTALL | re.IGNORECASE,
            )
            if d2:
                text = re.sub(r'<[^>]+>', '', d2.group(1))
                text = html_module.unescape(text)
                text = re.sub(r'\s+', ' ', text).strip()
                return _clean_inci(text) if len(text) > 20 else None
    return None


def _extract_deyga(page_html: str) -> str | None:
    """Extract INCI from Deyga's JSON-LD Product description field.

    The ingredients drawer is AJAX-loaded (empty in static/Playwright HTML). INCI is
    in the JSON-LD description as a hyphen-prefixed list after "Ingredients\n".
    """
    import json
    for block in re.finditer(
        r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
        page_html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(block.group(1).strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or data.get("@type") != "Product":
            continue
        desc = data.get("description") or ""
        m = re.search(r'\bIngredients\b\s*\n([\s\S]+)', desc)
        if not m:
            continue
        raw = m.group(1)
        # Stop at next section (blank line followed by capital word)
        stop = re.search(r'\n\s*\n[A-Z]', raw)
        if stop:
            raw = raw[:stop.start()]
        # Parse hyphen-prefixed list items (-item) or comma-separated
        items = []
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith('-'):
                item = line[1:].strip()
                if item:
                    items.append(item)
        if items:
            return _clean_inci(', '.join(items))
        # Fallback: treat as comma-separated INCI
        raw = raw.strip()
        return _clean_inci(raw) if len(raw) > 20 else None
    return None


def _extract_dearist(page_html: str) -> str | None:
    """Extract INCI from The Dearist's tab-content-1 section.

    First <p> in metafield-rich_text_field is marketing copy; INCI follows a
    "Full Ingredient List" heading paragraph. iS Clinical resold products have
    INCI directly in p[0] and are caught by the _looks_like_inci fallback.
    """
    from scraper.ingredient_schema_detector import _looks_like_inci
    tab_m = re.search(
        r'<div[^>]*class="[^"]*tab-content[^"]*tab-content-1[^"]*"[^>]*>',
        page_html, re.IGNORECASE,
    )
    if not tab_m:
        return None
    chunk = page_html[tab_m.start(): tab_m.start() + 10_000]
    meta_m = re.search(
        r'<div[^>]*class="[^"]*metafield-rich_text_field[^"]*"[^>]*>(.*?)</div\s*>',
        chunk, re.DOTALL | re.IGNORECASE,
    )
    if not meta_m:
        return None
    content = meta_m.group(1)
    p_tags = re.findall(r'<p[^>]*>(.*?)</p\s*>', content, re.DOTALL | re.IGNORECASE)
    cleaned = []
    for p in p_tags:
        text = re.sub(r'<[^>]+>', '', p)
        text = html_module.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        if text:
            cleaned.append(text)

    # Look for "Full Ingredient List" heading, INCI is in the following paragraph
    for i, text in enumerate(cleaned):
        if re.match(r'^\s*Full\s+Ingredient(?:s)?\s+(List\s*)?$', text, re.IGNORECASE):
            if i + 1 < len(cleaned) and len(cleaned[i + 1]) > 10:
                # Heading confirmed — trust content without _looks_like_inci (botanical/Ayurvedic names)
                return _clean_inci(cleaned[i + 1])
        # Inline: "Full Ingredient List: Aqua, ..."
        inline = re.match(r'^\s*Full\s+Ingredient(?:s)?\s+List\s*:\s*(.+)', text, re.IGNORECASE | re.DOTALL)
        if inline:
            raw = inline.group(1).strip()
            if len(raw) > 10:
                # Heading confirmed — trust content without _looks_like_inci
                return _clean_inci(raw)

    # Fallback: first INCI-like paragraph (works for iS Clinical resold products)
    for text in cleaned:
        if _looks_like_inci(text):
            return _clean_inci(text)
    # Final fallback: single-ingredient pure oils/extracts — short, botanical name with Latin in ()
    # e.g. "Cold-Pressed Apricot Kernel Oil (Prunus armeniaca)"
    if cleaned and len(cleaned[0]) < 200 and re.search(r'\([A-Z][a-z]+\s+[a-z]+', cleaned[0]):
        prose = ("it ", "this ", "our ", "helps ", "provides ", "is a ", "sourced from", "derived from")
        if not any(p in cleaned[0].lower() for p in prose):
            return _clean_inci(cleaned[0])
    return None


def _extract_barenecessities(page_html: str) -> str | None:
    """Extract INCI from Bare Necessities product pages.

    INCI is a raw text node following <strong>Ingredients:</strong>, sitting outside
    the tab <ul> container as a direct child of the grouped-content div.
    """
    m = re.search(r'<strong>\s*Ingredients\s*:?\s*</strong>', page_html, re.IGNORECASE)
    if not m:
        return None
    after = page_html[m.end(): m.end() + 3_000]
    # INCI is raw text before the next structural tag (<strong>, <div>, <ul>, <h>)
    stop = re.search(r'<(?:strong|div|ul|ol|h[1-6])\b', after, re.IGNORECASE)
    raw = after[:stop.start()] if stop else after[:2_000]
    # Strip any residual tags
    raw = re.sub(r'<[^>]+>', '', raw)
    raw = html_module.unescape(raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    return _clean_inci(raw) if len(raw) > 5 else None


def _extract_daughter_earth(page_html: str) -> str | None:
    """Extract INCI from Daughter Earth's Shogun page builder accordion or tab-pane.

    Two layouts are used:
    1. Accordion: <h4 class="shogun-accordion-title"> with an INCI-keyword title, followed
       by <div class="shogun-accordion-body"> containing the INCI text.
    2. Tab-pane: <div class="shogun-tab-pane"> — iterate panes and return the one that
       passes _looks_like_inci.

    The INCI may be split across nested <span>/<p> elements — strip all tags for plain text.
    """
    from scraper.ingredient_schema_detector import _looks_like_inci

    # --- Layout 1: accordion with INCI-keyword title ---
    h4_pat = re.compile(
        r'<h4[^>]*class="[^"]*shogun-accordion-title[^"]*"[^>]*>(.*?)</h4>',
        re.IGNORECASE | re.DOTALL,
    )
    for h4_m in h4_pat.finditer(page_html):
        title = re.sub(r'<[^>]+>', '', h4_m.group(1)).strip()
        # Match titles: "Ingredients", "Full Ingredients", "Ingredient list +",
        # "See Full INCI here", "INCI", etc.
        if not re.search(r'ingredi|INCI', title, re.IGNORECASE):
            continue
        after = page_html[h4_m.end(): h4_m.end() + 12_000]
        # Find the opening of the accordion body (may have nested divs, so don't use lazy match)
        body_open = re.search(r'<div[^>]*class="[^"]*shogun-accordion-body[^"]*"[^>]*>',
                              after, re.IGNORECASE)
        if not body_open:
            continue
        # Take a fixed chunk after the opening tag and strip all HTML.
        # Stop at the next shogun-accordion-item boundary to avoid spilling into adjacent items.
        body_start = body_open.end()
        next_item = re.search(r'<div[^>]*class="[^"]*shogun-accordion-item[^"]*"', after[body_start:], re.IGNORECASE)
        body_end = next_item.start() if next_item else 8_000
        chunk = after[body_start: body_start + min(body_end, 8_000)]
        text = re.sub(r'<[^>]+>', '', chunk)
        text = html_module.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 20 and _looks_like_inci(text[:200]):
            return _clean_inci(text)

    # --- Layout 2: shogun tab-panes (find the pane that looks like INCI) ---
    panes = re.findall(
        r'<div[^>]*class="[^"]*shogun-tab-pane[^"]*"[^>]*>(.*?)</div\s*>',
        page_html, re.DOTALL | re.IGNORECASE,
    )
    for pane in panes:
        text = re.sub(r'<[^>]+>', '', pane)
        text = html_module.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        if _looks_like_inci(text):
            return _clean_inci(text)

    return None


def _extract_inci_paragraph(container_selector: str, page_html: str) -> str | None:
    """Find the first INCI-like <p> inside a container; fall back to the longest paragraph.

    Used for Suhi & Sego where the INCI sits among key-ingredient marketing paragraphs —
    the correct one passes _looks_like_inci while the others are prose descriptions.
    """
    from scraper.ingredient_schema_detector import _selector_to_open_regex, _looks_like_inci
    open_pat = _selector_to_open_regex(container_selector)
    if not open_pat:
        return None
    m = re.search(open_pat, page_html, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    chunk = page_html[m.start(): m.start() + 10_000]
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p\s*>', chunk, re.DOTALL | re.IGNORECASE)
    if not paragraphs:
        return None
    cleaned = []
    for p in paragraphs:
        text = re.sub(r'<[^>]+>', '', p)
        text = html_module.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        if text:
            cleaned.append(text)
    if not cleaned:
        return None
    # Prefer first INCI-like paragraph; fall back to longest
    for text in cleaned:
        if _looks_like_inci(text):
            return _clean_inci(text)
    longest = max(cleaned, key=len)
    return _clean_inci(longest) if len(longest) > 30 else None


def _extract_raisebeauty(page_html: str) -> str | None:
    """Extract INCI from Raise Beauty's JSON-LD Product description.

    Description is HTML-encoded (e.g. <h5>Ingredients</h5><p>Water, ...</p>).
    Strip all HTML tags, then find text immediately after the 'Ingredients' heading.
    """
    import json
    for block in re.finditer(
        r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
        page_html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(block.group(1).strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or data.get("@type") != "Product":
            continue
        desc = data.get("description") or ""
        plain = re.sub(r'<[^>]+>', '\n', desc)
        plain = html_module.unescape(plain)
        plain = re.sub(r'\n{2,}', '\n', plain)
        m = re.search(r'\bIngredients\b\s*\n([\s\S]+)', plain)
        if m:
            raw = m.group(1)
            stop = re.search(r'\n[A-Z][A-Za-z\s]{3,}[\n:]', raw)
            if stop:
                raw = raw[:stop.start()]
            raw = raw.strip()
            return _clean_inci(raw) if len(raw) > 20 else None
    return None


def _extract_clayco(page_html: str) -> str | None:
    """Extract INCI from Clayco's INGREDIENTS accordion section.

    The page has multiple <ul class="metafield-single_line_text_field-array"> blocks
    (APPLICATION, INGREDIENTS, etc.). Find the one immediately following
    <strong>INGREDIENTS</strong> inside an accordion <summary>, then join all <li> text.
    """
    m = re.search(r'<strong>\s*INGREDIENTS\s*</strong>', page_html, re.IGNORECASE)
    if not m:
        return None
    chunk = page_html[m.start(): m.start() + 5_000]
    ul_m = re.search(r'<ul[^>]*class="[^"]*metafield-single_line_text_field-array[^"]*"[^>]*>(.*?)</ul\s*>',
                     chunk, re.DOTALL | re.IGNORECASE)
    if not ul_m:
        return None
    items = re.findall(r'<li[^>]*>(.*?)</li\s*>', ul_m.group(1), re.DOTALL | re.IGNORECASE)
    if not items:
        return None
    parts = [re.sub(r'<[^>]+>', '', item).strip() for item in items]
    parts = [html_module.unescape(p) for p in parts if p]
    return _clean_inci(', '.join(parts)) if parts else None


def _extract_quenchbotanics(page_html: str) -> str | None:
    """Extract INCI from Quench Botanics product pages.

    Three structures:
    1. <p><strong>Complete Ingredient List:</strong> Aqua, ...</p> — inline
    2. <p><strong>Complete Ingredient List:</strong></p><p>Aqua, ...</p> — split p tags
    3. JSON-LD Product.description with "(Complete) Ingredient List: ..." text
    """
    import json
    # Primary: paragraph containing "(Complete) Ingredient List:" in the page HTML (inline or split)
    m = re.search(
        r'<p[^>]*>(?:<[^>]+>)*\s*(?:Complete\s+)?Ingredient\s+List:?(?:</[^>]+>)*\s*(.*?)</p\s*>',
        page_html, re.DOTALL | re.IGNORECASE,
    )
    if m:
        raw = re.sub(r'<[^>]+>', '', m.group(0))
        raw = re.sub(r'^(?:Complete\s+)?Ingredient\s+List:?\s*', '', raw, flags=re.IGNORECASE).strip()
        if len(raw) > 20:
            return _clean_inci(raw)
        # Split-<p> case: heading in one <p>, INCI in the immediately following <p>
        after = page_html[m.end(): m.end() + 3_000]
        next_p = re.search(r'<p[^>]*>(.*?)</p\s*>', after, re.DOTALL | re.IGNORECASE)
        if next_p:
            raw2 = re.sub(r'<[^>]+>', '', next_p.group(1))
            raw2 = html_module.unescape(re.sub(r'\s+', ' ', raw2)).strip()
            if len(raw2) > 20:
                return _clean_inci(raw2)
    # Fallback: JSON-LD Product description
    for block in re.finditer(
        r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
        page_html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(block.group(1).strip())
            if isinstance(data, list):
                data = next((d for d in data if isinstance(d, dict) and d.get('@type') == 'Product'), {})
            if not isinstance(data, dict) or data.get('@type') != 'Product':
                continue
            desc = data.get('description') or ''
            jm = re.search(r'(?:[Cc]omplete\s+)?[Ii]ngredient\s+[Ll]ist\s*:\s*(.+)', desc, re.DOTALL)
            if jm:
                raw = jm.group(1).strip()
                stop = re.search(r'\n\n[A-Z]', raw)
                if stop:
                    raw = raw[:stop.start()]
                if len(raw) > 20:
                    return _clean_inci(raw)
        except Exception:
            pass
    # Fallback: JSON-encoded product description string (Shopify inline JSON)
    # Matches "Complete Ingredient List:\xa0Water, ..." terminated by \n or end-of-string-literal
    jm2 = re.search(
        r'(?:[Cc]omplete\s+)?[Ii]ngredient\s+[Ll]ist:[\s\xa0]*((?:[^"\\]|\\[^n])+)',
        page_html,
    )
    if jm2:
        raw = jm2.group(1).strip().rstrip(',')
        raw = re.sub(r'\\[tn]', ' ', raw)
        raw = re.sub(r'\s+', ' ', raw).strip()
        if len(raw) > 20:
            return _clean_inci(raw)
    return None


def _extract_biestyle(page_html: str) -> str | None:
    """Extract INCI from BiE (Beauty by BoE) accordion-tab pages.

    Tab position varies across products, so we scan all accordion-tab elements
    and find the one whose <summary> contains 'ingredient'. Returns the first
    <p> inside that tab's .accordion__content that passes _looks_like_inci.
    """
    from scraper.ingredient_schema_detector import _looks_like_inci
    all_tabs = re.findall(
        r'<accordion-tab[^>]*>(.*?)</accordion-tab>',
        page_html, re.DOTALL | re.IGNORECASE,
    )
    for tab in all_tabs:
        summaries = re.findall(r'<summary[^>]*>(.*?)</summary', tab, re.DOTALL | re.IGNORECASE)
        summary_text = re.sub(r'<[^>]+>', '', summaries[0]).strip() if summaries else ''
        if 'ingredient' not in summary_text.lower():
            continue
        ps = re.findall(r'<p[^>]*>(.*?)</p\s*>', tab, re.DOTALL | re.IGNORECASE)
        for p in ps:
            text = re.sub(r'<[^>]+>', '', p)
            text = html_module.unescape(text)
            text = re.sub(r'\s+', ' ', text).strip()
            if _looks_like_inci(text):
                return _clean_inci(text)
    return None


def _extract_deconstruct(page_html: str) -> str | None:
    """Extract INCI from The Deconstruct's 3rd accordion-tab.

    Tab 3 is "PRODUCT INGREDIENTS". Its .accordion__content starts with a heading
    <p>PRODUCT INGREDIENTS</p>; the actual INCI is in the following <p>.
    """
    from scraper.ingredient_schema_detector import _looks_like_inci
    all_tabs = re.findall(
        r'<accordion-tab[^>]*>(.*?)</accordion-tab>',
        page_html, re.DOTALL | re.IGNORECASE,
    )
    if len(all_tabs) < 3:
        return None
    tab3 = all_tabs[2]
    m = re.search(r'class="[^"]*accordion__content[^"]*"[^>]*>', tab3, re.IGNORECASE)
    if not m:
        return None
    chunk = tab3[m.start(): m.start() + 8_000]
    # Try <p> elements first, then <span> (newer template uses <span style="font-weight: 400;">)
    for tag_pat in (r'<p[^>]*>(.*?)</p\s*>', r'<span[^>]*>(.*?)</span\s*>'):
        elements = re.findall(tag_pat, chunk, re.DOTALL | re.IGNORECASE)
        for el in elements:
            text = re.sub(r'<[^>]+>', '', el)
            text = html_module.unescape(text)
            text = re.sub(r'\s+', ' ', text).strip()
            if _looks_like_inci(text):
                return _clean_inci(text)
    return None


def _extract_kiehls(page_html: str) -> str | None:
    """Extract INCI from Kiehl's ingredients-popup-inner div.

    Kiehl's uses two inner structures inside .ingredients-popup-inner:
    1. <div class="ingredient"> / <div class="All INGREDIENTS "> — ingredient per <p> tag
       (newline-separated format). We join all <p> texts with ", ".
    2. Inline comma-separated text (older pages) — validated via _looks_like_inci.
    Placeholder value "0" (product without INCI) is filtered out.
    """
    from scraper.ingredient_schema_detector import _looks_like_inci
    popup_m = re.search(
        r'<div[^>]*class="[^"]*ingredients-popup-inner[^"]*"[^>]*>',
        page_html, re.IGNORECASE,
    )
    if not popup_m:
        return None
    chunk = page_html[popup_m.start(): popup_m.start() + 10_000]

    # Structure 1: ingredient container div with one <p> per INCI entry
    ing_div = re.search(
        r'<div[^>]*class="[^"]*ingredi[^"]*"[^>]*>(.*?)</div\s*>',
        chunk, re.DOTALL | re.IGNORECASE,
    )
    if ing_div:
        ps = re.findall(r'<p[^>]*>(.*?)</p\s*>', ing_div.group(1), re.DOTALL | re.IGNORECASE)
        if ps:
            items = [re.sub(r'\s+', ' ', html_module.unescape(re.sub(r'<[^>]+>', '', p))).strip()
                     for p in ps]
            items = [i for i in items if i and i != '0']
            if items:
                joined = ', '.join(items)
                if _looks_like_inci(joined):
                    return _clean_inci(joined)

    # Structure 2: comma-separated inline (original path)
    m = re.search(
        r'<div[^>]*class="[^"]*ingredients-popup-inner[^"]*"[^>]*>(.*?)</div\s*>',
        page_html, re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return None
    text = re.sub(r'<[^>]+>', '', m.group(1))
    text = html_module.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return _clean_inci(text) if text and _looks_like_inci(text) else None


def _extract_pixiin(page_html: str) -> str | None:
    """Extract INCI from Pixi India (in.pixibeauty.com) product pages.

    INCI is in the "Ingredients" accordion section — specifically the
    .accordion-content-wrap-inner div that corresponds to the accordion button
    labelled "Ingredients".  The page template renders three accordion sections
    (Product Details / How To Apply / Ingredients); their content divs appear in
    the same order as the buttons.

    For bundle/set products the accordion shows only feature bullets, but the
    full INCI for each sub-product is in the .ingredients-popup__inner div
    (div.font-roboto) which is pre-populated in static HTML even though the popup
    is visually hidden.  We check the popup as a fallback when the accordion
    content fails _looks_like_inci.

    Bundles, kits, and brush pages show marketing feature bullets rather than a
    real INCI list in their "Ingredients" accordion.  We validate with
    _looks_like_inci to skip those.

    Products using the GWP/custom-template have no accordion at all and should
    have been pre-marked no_inci_html before reaching this extractor.
    """
    from scraper.ingredient_schema_detector import _looks_like_inci

    # Find accordion title buttons to locate the "Ingredients" position
    title_matches = list(re.finditer(
        r'<button[^>]*accordion-title[^>]*>(.*?)</button>',
        page_html, re.DOTALL | re.IGNORECASE,
    ))
    ingredients_idx = None
    for i, m in enumerate(title_matches):
        label = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        label = re.sub(r'\s+', ' ', label).strip()
        if re.search(r'\bingredient', label, re.IGNORECASE):
            ingredients_idx = i
            break

    if ingredients_idx is not None:
        # Collect all accordion-content-wrap-inner divs (one per accordion section)
        inner_matches = list(re.finditer(
            r'<div[^>]*accordion-content-wrap-inner[^>]*>(.*?)</div>',
            page_html, re.DOTALL | re.IGNORECASE,
        ))
        if ingredients_idx < len(inner_matches):
            raw_html = inner_matches[ingredients_idx].group(1)
            text = re.sub(r'<[^>]+>', ' ', raw_html)
            text = html_module.unescape(text)
            text = re.sub(r'\s+', ' ', text).strip()
            if text and _looks_like_inci(text):
                return _clean_inci(text)

    # Fallback: ingredients-popup__inner div.font-roboto — present in static HTML
    # for bundle/set products where each sub-product's INCI is pre-populated.
    popup_m = re.search(
        r'<div[^>]*class="[^"]*ingredients-popup__inner[^"]*"[^>]*>(.*?)</div\s*>\s*</div\s*>',
        page_html, re.DOTALL | re.IGNORECASE,
    )
    if not popup_m:
        # Broader match: find the inner content div inside the popup
        popup_m = re.search(
            r'<div[^>]*ingredients-popup__inner[^>]*>(.*?)(?=<div[^>]*ingredients-popup|$)',
            page_html, re.DOTALL | re.IGNORECASE,
        )
    if popup_m:
        popup_content = popup_m.group(1)
        # Extract text from the font-roboto div inside the popup
        roboto_m = re.search(
            r'<div[^>]*class="[^"]*font-roboto[^"]*"[^>]*>(.*?)(?=</div\s*>\s*</div\s*>|$)',
            popup_content, re.DOTALL | re.IGNORECASE,
        )
        raw_html = roboto_m.group(1) if roboto_m else popup_content
        text = re.sub(r'<[^>]+>', ' ', raw_html)
        text = html_module.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        if text and len(text) > 20:
            return _clean_inci(text)

    return None


def _extract_brillare(page_html: str) -> str | None:
    """Extract ingredient list from Brillare (brillare.co.in) product pages.

    Liquid formulas have a "FULL INGREDIENTS LIST" section containing <details>
    elements, each with a <summary><p> that names the ingredient.  Some products
    name the INCI in parentheses (e.g. "Aloe vera juice (aloe barbadensis leaf
    juice)"); others use the INCI directly as the ingredient name.  Powder-format
    products and kits have no such section and return None.
    """
    idx = page_html.upper().find("FULL INGREDIENTS LIST")
    if idx < 0:
        return None

    section = page_html[idx: idx + 15_000]

    details_blocks = re.findall(
        r"<details[^>]*>(.*?)</details>", section, re.DOTALL | re.IGNORECASE
    )

    ingredients = []
    for d in details_blocks:
        s_m = re.search(r"<summary[^>]*>(.*?)</summary>", d, re.DOTALL | re.IGNORECASE)
        if not s_m:
            continue
        p_m = re.search(r"<p[^>]*>(.*?)</p>", s_m.group(1), re.DOTALL | re.IGNORECASE)
        if not p_m:
            continue
        text = html_module.unescape(re.sub(r"<[^>]+>", "", p_m.group(1))).strip()
        text = re.sub(r"\s+", " ", text)

        # When INCI is in parentheses (e.g. "Marketing name (inci name)"), prefer the INCI
        paren_m = re.search(r"\(([^)]+)\)", text)
        inci = paren_m.group(1).strip() if paren_m else text

        if inci and len(inci) > 2:
            ingredients.append(inci)

    if not ingredients:
        return None

    return ", ".join(ingredients)


def _extract_juicychemistry(page_html: str) -> str | None:
    """Extract INCI from Juicy Chemistry (juicychemistry.com) product pages.

    INCI lives inside a <details class="accordion ..."> block whose summary
    contains "know our ingredients".  Products range from single-ingredient
    botanical oils ("Lavandula Angustifolia (Lavender) Oil*") to multi-ingredient
    formulas with a "Full Ingredients List: ..." line.

    Footnote lines ("*Ingredient from Organic Farming", COSMOS certification
    text) and long ingredient-description prose lines are skipped.
    """
    _FOOTNOTE = re.compile(
        r"^\*|from [Oo]rganic [Ff]arming|of the total ingredient"
        r"|COSMOS|Ecocert|subject to change|^-->",
        re.IGNORECASE,
    )

    details_blocks = re.findall(
        r"<details[^>]*class=\"[^\"]*accordion[^\"]*\"[^>]*>(.*?)</details>",
        page_html, re.DOTALL | re.IGNORECASE,
    )

    for block in details_blocks:
        if "know our ingredient" not in block.lower():
            continue

        ps = re.findall(r"<p[^>]*>(.*?)</p\s*>", block, re.DOTALL | re.IGNORECASE)
        for p in ps:
            text = html_module.unescape(re.sub(r"<[^>]+>", " ", p))
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue

            # "Full Ingredients List:" anywhere in text — check before footnote skip
            # because some p tags embed both description and INCI in one element
            fll_m = re.search(
                r"[Ff]ull [Ii]ngredients? [Ll]ist\s*:\s*(.+)", text
            )
            if fll_m:
                raw = fll_m.group(1)
                # Strip trailing standalone footnote ("*Ingredients are from..." etc.)
                raw = re.sub(r"\s*\*[A-Z].*", "", raw)
                raw = raw.rstrip("*.").strip()
                if len(raw) > 5:
                    return _clean_inci(raw)

            if _FOOTNOTE.search(text):
                continue

            # Single-ingredient botanical INCI: short text with 2+ multi-char capitalized words
            # (Latin binomials like "Lavandula Angustifolia" have both words capitalized).
            # Cap at 100 chars to avoid matching description prose (e.g. "Rose Water: A soothing...")
            if len(text) < 100 and len(re.findall(r"[A-Z][a-z]{3,}", text)) >= 2:
                return _clean_inci(text)

            from scraper.ingredient_schema_detector import _looks_like_inci
            if _looks_like_inci(text):
                return _clean_inci(text)

        break  # only process first matching block

    return None


def _extract_letshyphen(page_html: str) -> str | None:
    """Extract INCI from Let's Hyphen (letshyphen.com) product pages.

    The Shopify theme stores product tab content in a JavaScript Products[] blob
    with ##field_name: @@value## delimiters.  The INCI is found after
    '##Ingredients:' (or '##Ingredient:') and starts after '@@', ending at the
    next '##' delimiter or end of the JS string.
    """
    m = re.search(r'##[Ii]ngredient[s]?\s*:\s*@@(.*?)(?=##|$)', page_html, re.DOTALL)
    if not m:
        return None
    raw = m.group(1).strip()
    # Strip any trailing JS string quote or escape sequences
    raw = re.sub(r'["\'].*$', '', raw, flags=re.DOTALL)
    raw = re.sub(r'\\[nrt]', ' ', raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    return _clean_inci(raw) if len(raw) > 10 else None


def _extract_dabtofab(page_html: str) -> str | None:
    """Extract INCI from Dab to Fab (dabtofab.co) product pages.

    INCI is in a <p> inside .accordion-content following the <h3> "Full Ingredients"
    heading inside the product description accordion.
    """
    m = re.search(r'Full\s+Ingredients?', page_html, re.IGNORECASE)
    if not m:
        return None
    # Look for .accordion-content div after this heading
    after = page_html[m.start(): m.start() + 3_000]
    content_m = re.search(
        r'<div[^>]*class="[^"]*accordion-content[^"]*"[^>]*>(.*?)</div\s*>',
        after, re.DOTALL | re.IGNORECASE,
    )
    if content_m:
        raw = re.sub(r'<[^>]+>', '', content_m.group(1))
        raw = html_module.unescape(raw)
        raw = re.sub(r'\s+', ' ', raw).strip()
        if len(raw) > 10:
            return _clean_inci(raw)
    # Fallback: find the <p> immediately following "Full Ingredients" heading
    p_m = re.search(r'<p[^>]*>(.*?)</p\s*>', after, re.DOTALL | re.IGNORECASE)
    if p_m:
        raw = re.sub(r'<[^>]+>', '', p_m.group(1))
        raw = html_module.unescape(raw)
        raw = re.sub(r'\s+', ' ', raw).strip()
        if len(raw) > 10:
            return _clean_inci(raw)
    return None


def _extract_hibiscusmonkey(page_html: str) -> str | None:
    """Extract INCI from Hibiscus Monkey (hibiscusmonkey.com) product pages.

    The ingredient list is in a Bootstrap modal table (.accordion_container) where
    each entry is a pair of .pop-ingrd-accrdion-heading divs: the first has the
    ingredient name in <strong>, the second has the source (Natural/Synthetic) as plain text.
    We collect all <strong>-wrapped entries and join with ", ".
    """
    # Scope to the accordion_container section to avoid false positives elsewhere
    container_m = re.search(r'<div[^>]*class="[^"]*accordion_container[^"]*"', page_html, re.IGNORECASE)
    search_html = page_html[container_m.start(): container_m.start() + 30_000] if container_m else page_html

    # Every ingredient name is in a pop-ingrd-accrdion-heading div wrapping a <strong> tag.
    ingredients = []
    for m in re.finditer(
        r'<div[^>]*pop-ingrd-accrdion-heading[^>]*>\s*<strong[^>]*>(.*?)</strong>',
        search_html, re.DOTALL | re.IGNORECASE,
    ):
        name = re.sub(r'<[^>]+>', '', m.group(1))
        name = html_module.unescape(name)
        name = re.sub(r'\s+', ' ', name).strip()
        if name:
            ingredients.append(name)

    if not ingredients:
        return None
    return _clean_inci(', '.join(ingredients))


def _clean_inci(raw: str) -> str:
    """Strip HTML tags, decode entities, normalize whitespace."""
    no_tags = re.sub(r"<[^>]+>", "", raw)
    decoded = html_module.unescape(no_tags)
    cleaned = re.sub(r"\s+", " ", decoded).strip()
    return cleaned
