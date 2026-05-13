"""Fetch Shopify /products.json — optionally via ScraperAPI proxy."""
from __future__ import annotations

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = structlog.get_logger()

# Retry chain for 403/429 responses:
#   1. direct          — no proxy, fastest, free
#   2. scraperapi      — datacenter proxy, costs ~1 credit/request
#   3. scraperapi_res  — residential proxy, costs ~25 credits/request, last resort
_PROXY_LEVELS = ("direct", "scraperapi", "scraperapi_residential")


def _build_client(scraperapi_key: str, residential: bool = False) -> httpx.AsyncClient:
    kwargs: dict = {"timeout": 60.0}
    if scraperapi_key:
        if residential:
            # residential=true instructs ScraperAPI to route through residential IPs
            kwargs["proxy"] = f"http://scraperapi.residential=true:{scraperapi_key}@proxy-server.scraperapi.com:8001"
        else:
            kwargs["proxy"] = f"http://scraperapi:{scraperapi_key}@proxy-server.scraperapi.com:8001"
        kwargs["verify"] = False  # ScraperAPI proxy uses its own SSL cert
    return httpx.AsyncClient(**kwargs)


@retry(
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    reraise=True,
)
async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    resp = await client.get(url)
    resp.raise_for_status()
    return resp


async def fetch_shopify_products(
    url: str, scraperapi_key: str = "", collection_handle: str | None = None
) -> str:
    """Fetch all products via paginated API, return combined JSON string.

    If collection_handle is given, uses /collections/{handle}/products.json which
    returns only storefront-visible products (excludes gifts, free samples, bundles).

    Retry chain on 403/429:
      direct → ScraperAPI datacenter → ScraperAPI residential (last resort, expensive)
    """
    import json

    base_domain = url.split("/products.json")[0].split("?")[0]
    base = (
        f"{base_domain}/collections/{collection_handle}/products.json"
        if collection_handle
        else f"{base_domain}/products.json"
    )

    all_products = []
    page = 1
    proxy_level = 0  # index into _PROXY_LEVELS; escalates on 403/429

    clients = [
        _build_client(""),                                    # direct
        _build_client(scraperapi_key),                        # datacenter
        _build_client(scraperapi_key, residential=True),      # residential
    ]

    async with clients[0] as direct, clients[1] as standard, clients[2] as residential:
        active_clients = [direct, standard, residential]

        while True:
            paged_url = f"{base}?limit=250&page={page}"
            client = active_clients[proxy_level]
            via = _PROXY_LEVELS[proxy_level]
            log.info("shopify_fetch", url=paged_url, via=via, page=page)

            try:
                resp = await _get(client, paged_url)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in (403, 429) and proxy_level < len(_PROXY_LEVELS) - 1:
                    proxy_level += 1
                    next_via = _PROXY_LEVELS[proxy_level]
                    # Skip residential if no key provided
                    if next_via == "scraperapi_residential" and not scraperapi_key:
                        raise
                    if next_via == "scraperapi" and not scraperapi_key:
                        raise
                    log.warning("shopify_blocked_escalating",
                                url=paged_url, status=status, next=next_via)
                    client = active_clients[proxy_level]
                    resp = await _get(client, paged_url)
                else:
                    raise

            batch = resp.json().get("products", [])
            if not batch:
                break
            all_products.extend(batch)
            if len(batch) < 250:
                break
            page += 1

    return json.dumps({"products": all_products})


async def fetch_brand_collections(base_url: str, scraperapi_key: str = "") -> list[dict]:
    """Fetch all collections for a Shopify store."""
    import json as _json

    base_domain = base_url.rstrip("/")
    url = f"{base_domain}/collections.json?limit=250"

    async with _build_client(scraperapi_key) as client:
        log.info("shopify_fetch_collections", url=url)
        resp = await _get(client, url)
        collections_raw = resp.json().get("collections", [])

    return [
        {"id": c["id"], "handle": c["handle"], "title": c["title"]}
        for c in collections_raw
        if c.get("id") and c.get("handle") and c.get("title")
    ]
