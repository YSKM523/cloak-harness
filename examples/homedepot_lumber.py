"""Example: scrape 2x4 lumber prices from Home Depot Canada.

Run via:
    export BU_CDP_URL=http://127.0.0.1:9222
    browser-harness -c "$(cat examples/homedepot_lumber.py)"

Or as a shell pipeline:
    browser-harness -c "$(cat examples/homedepot_lumber.py)" | tee lumber.json

Assumes:
    1. CloakBrowser stealth Chromium is running on 127.0.0.1:9222
       (start via `scripts/start-cloak.sh`).
    2. agent_helpers.py is symlinked into browser-harness's agent-workspace
       (so `human_click_at_xy` and friends are importable).

Demonstrates the pieces this repo adds on top of upstream:
    - human_move_to before clicking, so the page sees real mouse traffic
      before any interaction.
    - human_scroll_into_view_selector to surface lazy-loaded products.
    - js() extraction via the harness CDP path.
"""

import json
import re
import time


SEARCH_URL = "https://www.homedepot.ca/search?q=2+in+x+4+in+spruce"


def extract_products(text: str):
    """Pair product titles with their dollar-and-cents prices from the
    page's flat innerText. Home Depot CA renders prices split across lines
    like `$13\nAnd\n48\nCents` which a naive regex misses.
    """
    lines = text.split("\n")
    products = []
    seen = set()

    for i, line in enumerate(lines):
        # Match real 2x4 product titles, not pressure-treated / cedar variants
        # unless explicitly 2x4.
        if not re.search(r"\b2(?:[\s\-]*in(?:ch)?)?\s*[xX]\s*4\b", line):
            continue
        if line.startswith("$") or len(line) > 120:
            continue

        # Look ahead for the price pattern: $NN \n And \n NN \n Cents
        window = lines[i : i + 12]
        price = None
        for j in range(len(window) - 3):
            dollars = window[j].strip()
            if (
                dollars.startswith("$")
                and j + 2 < len(window)
                and window[j + 1].strip().lower() == "and"
            ):
                d = re.match(r"\$(\d+)", dollars)
                c = re.match(r"(\d+)", window[j + 2].strip())
                if d and c:
                    price = f"${d.group(1)}.{int(c.group(1)):02d}"
                    break

        if not price:
            continue
        title = line.strip()
        # Home Depot renders each card's title twice (top + bottom of card).
        # The lookahead picks up the next card's price for the second copy,
        # so keep only the first occurrence per title.
        if title in seen:
            continue
        seen.add(title)
        products.append({"title": title, "price_cad": price})

    return products


# --- harness flow ---

print(f"navigating to {SEARCH_URL}", flush=True)
goto_url(SEARCH_URL)
wait_for_load(timeout=30)
time.sleep(4)  # let lazy product cards render

info = page_info()
print(f"landed on: {info['url']}  ({info['title']})", flush=True)

# A touch of human motion before reading — surfaces real mouse traffic
# to any client-side scoring that runs on first interaction.
human_move_to(600, 400)
time.sleep(0.4)

# Scroll a bit to trigger any lazy-loading product cards.
js("window.scrollBy(0, 800)")
time.sleep(1.0)

# Grab the page's flat text and parse out 2x4 products with prices.
text = js("return document.body.innerText")
products = extract_products(text)

print(f"\nfound {len(products)} products:", flush=True)
for p in products:
    print(f"  {p['price_cad']:>8}  {p['title']}", flush=True)

print("\n--- JSON ---")
print(json.dumps({"source": SEARCH_URL, "products": products}, indent=2))
