# Reverse-engineering site APIs

Scraping rendered HTML/innerText is the wrong default. It's slow, fragile (selectors break on every redesign), and you only see what the page chose to render. The right pattern is:

1. Use the stealth browser to **get past the anti-bot layer once** — load any page, let cookies and CF clearance tokens populate.
2. Then **call the site's JSON APIs directly** from inside the page's JS context. Cookies, CSRF tokens, anti-bot headers all attach automatically.
3. Loop the API call for pagination/filters; no more page navigations.

This is dramatically faster (one ~200KB JSON request vs a full page render) and returns clean structured data (numbers, not formatted strings).

## The two helpers in this repo

`agent_helpers.py` exposes two functions that make this workflow easy:

```python
install_xhr_recorder()     # injects fetch/XHR interceptor (survives navigations)
recorded_requests(only_json=True, host_substr="example.com")  # read captured requests
page_fetch_json(url, headers=None, method="GET", body=None)   # call API from page context
```

`install_xhr_recorder()` hooks both `window.fetch` and `XMLHttpRequest` via `Page.addScriptToEvaluateOnNewDocument`, so it captures everything from the moment a new document loads — including requests that fire before any user code runs.

## Workflow

### Step 1: Observe what the site actually requests

```python
install_xhr_recorder()
goto_url("https://target.com/search?q=widget")
wait(8)  # let the page settle and lazy-loaded XHRs fire

for r in recorded_requests(only_json=True, host_substr="target.com"):
    print(f"[{r['method']} {r['status']}] {r['url'][:120]}")
    print(f"  body: {r['bodyHead'][:200]}")
```

This prints every JSON-shaped response: URL, status, content-type, and first 600 chars of body. Look for endpoints with names like `/api/...`, `/v1/...`, `/graphql`, or `*.json`.

### Step 2: Identify the data endpoint

Among the captured requests, the data endpoint is usually one of:

- A REST search endpoint: `/api/v1/search?q=...&page=...&pageSize=...`
- A GraphQL endpoint: `/graphql` (POST with `{query, variables}`)
- A category/listing endpoint: `/api/products?category=...&filter=...`

For Home Depot Canada, observation reveals:

```
GET /api/search/v1/search?q=2x4&page=1&pageSize=40&lang=en
→ {facets, metadata, products: [{name, pricing.displayPrice, modelNumber, ...}], ...}
```

### Step 3: Call the endpoint directly

```python
data = page_fetch_json("/api/search/v1/search?q=2x4&page=1&pageSize=40&lang=en")
for p in data["products"]:
    print(p["name"], p["pricing"]["displayPrice"]["formattedValue"])
```

`page_fetch_json` runs inside the page's JS context, so:
- Cookies attach automatically (including any anti-bot clearance cookies the page acquired).
- Same-origin headers like `Referer` and `Origin` are correct.
- CSP doesn't block the call (same context as the page itself).
- The TLS connection is the browser's, so JA3 matches what the site has already approved.

### Step 4: Paginate and filter

Most API endpoints accept `page` / `offset` / `cursor` parameters. Loop until empty:

```python
all_items = []
for page in range(1, 50):
    data = page_fetch_json(f"/api/search/v1/search?q=2x4&page={page}&pageSize=40&lang=en")
    items = data.get("products") or []
    if not items:
        break
    all_items.extend(items)
    time.sleep(0.4)  # courtesy pacing
```

## When this approach fails

1. **The site renders entirely server-side** (e.g., classical PHP rendering, no JSON XHRs). Rare on modern sites. Fall back to HTML parsing.
2. **GraphQL with persisted queries** — the site only accepts a known query hash, not arbitrary queries. You can usually still replay the exact hash + variables observed during normal use.
3. **Request signing** — the request URL or body contains a signature derived from JS that runs in the page. Two options:
   - Replay the request observed by `recorded_requests()` exactly (the signature is one-time and time-limited but works for a short window).
   - Trace the signing code in DevTools and reimplement it (high effort, but durable).
4. **The endpoint enforces stricter bot-detection than the page** — rare. If it happens, route the request through the page like `page_fetch_json` does instead of using a Python `requests` library.

## Pacing and ethics

Calling an API directly is dramatically faster than browsing — easy to fire hundreds of requests per minute. Don't:

- Add courtesy delays between requests (200-800ms is reasonable).
- Respect `robots.txt` for what you're scraping (the `/api/` paths usually aren't covered, but the data being returned often is).
- Don't scrape proprietary data you'd be sued for republishing.
- If the site rate-limits you, back off; don't rotate proxies to circumvent it.
- Identify yourself if you're doing this commercially or at scale (set `User-Agent` via a custom header, or contact the site for an official API key).

## See also

- [`examples/homedepot_lumber.py`](../examples/homedepot_lumber.py) — innerText baseline.
- [`examples/homedepot_lumber_api.py`](../examples/homedepot_lumber_api.py) — same target via the discovered JSON API.
