"""Inspect categoryListing.listingData structure."""
import json, re

with open("/tmp/nykaa_cat_0.html") as f:
    html = f.read()

idx = html.find("window.__PRELOADED_STATE__")
start = html.index("{", idx)
end = html.find("</script>", start)
state = json.loads(html[start:end].rstrip("; \n"))

cl = state.get("categoryListing", {})
ld = cl.get("listingData", {})

print("listingData type:", type(ld).__name__)
print("listingData keys:", list(ld.keys()) if isinstance(ld, dict) else f"list of {len(ld)}")

if isinstance(ld, dict):
    for k, v in ld.items():
        if isinstance(v, list) and v:
            print(f"\n  {k}: list({len(v)})")
            if isinstance(v[0], dict):
                print(f"  [0] keys: {list(v[0].keys())[:20]}")
                item = v[0]
                for fk in ["name", "slug", "brandName", "mrp", "offerPrice", "id", "url", "productUrl"]:
                    if fk in item:
                        print(f"    {fk} = {repr(item[fk])[:80]}")
        else:
            print(f"  {k}: {type(v).__name__} = {repr(v)[:80]}")
elif isinstance(ld, list) and ld:
    print(f"\nFirst item keys: {list(ld[0].keys())[:20]}")
    item = ld[0]
    for fk in ["name", "slug", "brandName", "mrp", "offerPrice", "id", "url"]:
        if fk in item:
            print(f"  {fk} = {repr(item[fk])[:80]}")
