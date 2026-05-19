"""Example: scrape 2x4 lumber from Home Depot Canada via their internal
JSON search API.

Compared to the innerText version (homedepot_lumber.py), this approach:
    - Is 10-50x faster (one ~200KB JSON request vs full page render)
    - Returns structured data (price as float, stock status, model #, ratings)
    - Doesn't break when the site redesigns
    - Naturally handles pagination (no scrolling needed)

The tradeoff: you have to discover the API endpoint first. See
`docs/reverse-engineering.md` for the methodology.

Endpoint:
    GET /api/search/v1/search?q=<query>&page=N&pageSize=N&lang=en
    Returns: {products: [{name, pricing.displayPrice, modelNumber, ...}], ...}

Run via:
    export BU_CDP_URL=http://127.0.0.1:9222
    browser-harness -c "$(cat examples/homedepot_lumber_api.py)"
"""

import json
import re
import time


HOST = "https://www.homedepot.ca"


def normalize(p):
    pricing = p.get("pricing") or {}
    dp = pricing.get("displayPrice") or {}
    rating = p.get("productRating") or {}
    return {
        "name": p.get("name"),
        "price_cad": dp.get("value"),
        "price_formatted": dp.get("formattedValue"),
        "model": p.get("modelNumber"),
        "sku": p.get("code"),
        "url": HOST + (p.get("url") or ""),
        "in_stock": (p.get("stock") or {}).get("stockLevelStatus") == "inStock",
        "rating": rating.get("averageRating"),
        "reviews": rating.get("totalReviews"),
        "promo": (p.get("promotionMessages") or {}).get("stripeMessage"),
    }


# --- harness flow ---

# 1. Visit the homepage once so the browser gets cookies and clears any
#    interstitials. After that, all same-origin fetch() calls inherit the
#    session.
print(f"warming session on {HOST} ...", flush=True)
goto_url(HOST + "/en/home.html")
wait_for_load(timeout=30)
time.sleep(2)

# 2. Hit the JSON search API directly. page_fetch_json() makes a fetch() call
#    from inside the page's JS context, so cookies/anti-bot tokens attach
#    automatically.
all_products = []
for page in range(1, 3):  # first 2 pages = 80 products max
    print(f"fetching page {page} ...", flush=True)
    data = page_fetch_json(
        f"/api/search/v1/search?q=2x4&page={page}&pageSize=40&lang=en"
    )
    products = data.get("products") or []
    if not products:
        break
    all_products.extend(products)
    time.sleep(0.6)  # courtesy pacing

# 3. Filter to actual 2x4 products (Home Depot's "2x4" search includes
#    pressure-treated, cedar, and unrelated items because of the bigram).
pat = re.compile(r"\b2(?:[\s\-]*in(?:ch)?)?\s*[xX]\s*4\b")
records = [normalize(p) for p in all_products if p.get("name") and pat.search(p["name"])]

# Sort: in-stock first, then by price ascending
records.sort(key=lambda r: (not r["in_stock"], r["price_cad"] or 999999))

print(f"\nfound {len(records)} 2x4 products from {len(all_products)} total hits\n", flush=True)
print(f"{'PRICE':<10} {'STOCK':<10} {'RATING':<8} {'TITLE'}")
print("-" * 100)
for r in records[:20]:
    stock = "in" if r["in_stock"] else "out"
    rating = f"{r['rating']:.1f} ({r['reviews']})" if r["rating"] else "—"
    print(f"{r['price_formatted'] or '—':<10} {stock:<10} {rating:<8} {r['name']}")

print("\n--- JSON ---")
print(json.dumps({"source": "homedepot.ca/api/search/v1", "count": len(records), "products": records[:20]}, indent=2))
