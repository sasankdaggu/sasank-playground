"""Drill into Nykaa __PRELOADED_STATE__ product-relevant reducers."""
import json, re

with open("/tmp/nykaa_product.html") as f:
    html = f.read()

idx = html.find("window.__PRELOADED_STATE__")
start = html.index("{", idx)
end = html.find("</script>", start)
state = json.loads(html[start:end].rstrip("; \n"))

def show(obj, depth=0, max_depth=5):
    if depth > max_depth: return
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:40]:
            if isinstance(v, (dict, list)) and v:
                print(f"{'  '*depth}{k}: {type(v).__name__}({len(v)})")
                show(v, depth+1, max_depth)
            else:
                print(f"{'  '*depth}{k} = {repr(v)[:120]}")
    elif isinstance(obj, list) and obj:
        for i, item in enumerate(obj[:3]):
            print(f"{'  '*depth}[{i}]:")
            show(item, depth+1, max_depth)

print("=== productPage ===")
show(state["productPage"], max_depth=4)

print("\n\n=== jsonLdData ===")
show(state["jsonLdData"], max_depth=3)

print("\n\n=== priceReveal (top keys) ===")
show(state["priceReveal"], max_depth=2)

print("\n\n=== searchListingPage (top keys) ===")
show(state["searchListingPage"], max_depth=2)

# Also extract the application/ld+json
m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
if m:
    print("\n\n=== application/ld+json ===")
    data = json.loads(m.group(1))
    show(data, max_depth=4)
