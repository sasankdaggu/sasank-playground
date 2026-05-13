"""Directly examine saved HTML to understand Nykaa structure."""
import json, re

with open("/tmp/nykaa_product.html") as f:
    html = f.read()

print(f"Total size: {len(html):,} chars")

# Find __PRELOADED_STATE__
idx = html.find("window.__PRELOADED_STATE__")
print(f"\n__PRELOADED_STATE__ position: {idx}")
if idx >= 0:
    # Extract just the JSON - find the matching closing brace
    start = html.index("{", idx)
    # Simple extraction: take everything until script ends
    end = html.find("</script>", start)
    raw = html[start:end].rstrip("; \n")
    print(f"JSON blob size: {len(raw):,} chars")
    try:
        state = json.loads(raw)
        print("Top-level keys:", list(state.keys()))
        for k, v in state.items():
            print(f"  {k}: {type(v).__name__}({len(v) if isinstance(v, (dict,list)) else ''})")
    except json.JSONDecodeError as e:
        print(f"Parse error at pos {e.pos}: {e.msg}")
        print("Context:", raw[max(0,e.pos-50):e.pos+50])

# Find application/ld+json
print("\n\nSearching for ld+json...")
idx2 = html.find("application/ld+json")
print(f"Position: {idx2}")
if idx2 >= 0:
    print("Context:", html[idx2-50:idx2+200])

# Find all script type attributes
print("\n\nAll <script> opening tags:")
for m in re.finditer(r'<script([^>]*)>', html):
    attrs = m.group(1).strip()
    if attrs:
        print(f"  <script {attrs}>")
