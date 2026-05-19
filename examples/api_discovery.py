"""Example: full API discovery workflow on a real site.

Shows the four reverse-engineering helpers working together:

    1. install_xhr_recorder()       — capture fetch + XHR (incl. request bodies)
    2. detect_graphql()             — find GraphQL operations + queries + hashes
    3. detect_signed_requests()     — flag endpoints with signature/token params
    4. infer_schema()               — type-sketch the API response
    5. paginate_api()               — replay the endpoint across pages

Target: Home Depot Canada. Replace HOST and SEARCH_PATH for any site whose
internal API you want to map.

Run via:
    export BU_CDP_URL=http://127.0.0.1:9222
    browser-harness -c "$(cat examples/api_discovery.py)"
"""

import json
import time


HOST = "https://www.homedepot.ca"
WARMUP_URL = HOST + "/search?q=2x4"


# 1. Install recorder BEFORE any navigation. Hook survives navigations.
install_xhr_recorder()

# 2. Visit a real page so the site fires its real XHRs. Cookies populate.
print(f"warming on {WARMUP_URL} ...", flush=True)
goto_url(WARMUP_URL)
wait_for_load(timeout=30)
time.sleep(8)

# 3. Inspect captured traffic.
reqs = recorded_requests(only_json=True, host_substr="homedepot.ca")
print(f"\ncaptured {len(reqs)} same-origin JSON responses\n")

# Print everything in a digestible form.
for r in reqs[:10]:
    print(f"  [{r['method']} {r['status']}] {r['url'][:120]}")
    print(f"    ct: {r.get('ct','')[:60]}")
    print(f"    body: {r.get('bodyHead','')[:160]}")
    print()

# 4. GraphQL endpoints (none expected on Home Depot — they use REST).
print("--- GraphQL operations ---")
ops = detect_graphql()
if not ops:
    print("  (none — this site uses REST, not GraphQL)")
for op in ops:
    print(f"  {op['endpoint']}  op={op['operationName']}  count={op['count']}")
    if op["persistedQueryHash"]:
        print(f"    persisted hash: {op['persistedQueryHash']}")
    if op["query"]:
        print(f"    query: {op['query'][:100]}")
print()

# 5. Signed / token-carrying requests (alerts you to endpoints that need
#    page-context replay or signing logic reverse-engineering).
print("--- Signed / opaque-param requests ---")
flagged = detect_signed_requests()
if not flagged:
    print("  (none — clean URL params)")
for f in flagged[:6]:
    print(f"  {f['method']} {f['url'][:100]}")
    print(f"    → {f['reason']}")
print()

# 6. Pick the search endpoint we discovered and dump its response schema.
search_endpoint = "/api/search/v1/search?q=2x4&page=1&pageSize=2&lang=en"
print(f"--- Schema of {search_endpoint} ---")
sample = page_fetch_json(search_endpoint)
schema = infer_schema(sample, max_examples=1)
# Compact output — just the top-level and one product shape
print(json.dumps({
    "top_level": {k: (v if not isinstance(v, (dict, list)) else type(v).__name__) for k, v in sample.items()},
    "products[0] schema": schema.get("products", {}).get("_list_of") if isinstance(schema.get("products"), dict) else schema.get("products"),
}, indent=2, default=str)[:1500])
print()

# 7. Now that we know the endpoint shape, paginate it for real data.
print("--- Paginating /api/search/v1/search across 3 pages ---")
items = paginate_api(
    "/api/search/v1/search?q=2x4&page={page}&pageSize=20&lang=en",
    items_key="products",
    max_pages=3,
    sleep_seconds=0.4,
    on_page=lambda p, d, i: print(f"  page {p}: {len(i)} products"),
)
print(f"\ntotal collected: {len(items)} products")

# Quick summary
in_stock = sum(1 for p in items if (p.get("stock") or {}).get("stockLevelStatus") == "inStock")
print(f"  in stock:   {in_stock}")
print(f"  out stock:  {len(items) - in_stock}")
print(f"\nfirst 3 names:")
for p in items[:3]:
    name = p.get("name", "?")[:70]
    price = (p.get("pricing") or {}).get("displayPrice", {}).get("formattedValue", "?")
    print(f"  {price:<8} {name}")
