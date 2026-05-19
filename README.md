# cloak-harness

A bridge wiring [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) (stealth Chromium binary) and [browser-harness](https://github.com/browser-use/browser-harness) (LLM-driven CDP harness) so they cooperate cleanly: cloak provides the indistinguishable-from-real-Chrome process, browser-harness provides the agent control loop, and this repo adds the glue so cloak's human-like input flows through the harness's CDP path.

![cloak-harness demo](docs/media/demo.gif)

*Form filled by an LLM agent through `browser-harness`, with each keystroke and click going through `cloak`'s human-like input adapter (Bezier mouse trajectory, per-key timing, aim/hold delays). All inside a stealth Chromium that passes most bot-detection benchmarks. See [`docs/results.md`](docs/results.md) for the full table.*

## What this is and isn't

- **Is**: one integration helper module (`agent-workspace/agent_helpers.py`), launch scripts (`scripts/`), examples, and a documented setup recipe with honest benchmark results.
- **Is not** a new stealth engine — all browser fingerprint patches come from upstream CloakBrowser.
- **Is not** a new agent harness — all CDP wrapping, daemon, and agent loop come from upstream browser-harness.
- **Is not** a CAPTCHA solver. If the target shows a visible challenge widget, you still need a solver service.

## What it adds on top

1. **Adapter from cloak `RawMouse`/`RawKeyboard` to harness CDP**, so `human_move`, `human_click`, `human_type`, and `human_scroll_into_view` run through the same single CDP channel the harness already maintains.
2. **Helper functions** exposed to harness agents:
   - `human_click_at_xy(x, y, is_input=False)`
   - `human_move_to(x, y)`
   - `human_type_text(text)`
   - `human_scroll_into_view_selector(selector)`
   - `cursor_pos()`
3. **Bug fix for double-insertion** when `keyDown` carries `text` alongside a separate `char` event (the upstream `browser-harness.press_key` has the same issue — see `docs/known-issues.md`).
4. **Local upstream-auth HTTP CONNECT forwarder** (`scripts/proxy-forwarder.py`) for residential proxies that require Basic auth — Chromium's `--proxy-server` does not reliably pass inline credentials.
5. **Honest benchmarks** of what passes and what does not (`docs/results.md`).

## Architecture

```
    CloakBrowser stealth Chromium (xvfb display)
       │  CDP @ 127.0.0.1:9222
       │
    browser-harness daemon
       │  loads agent-workspace/agent_helpers.py
       │  → injects human_* helpers into the agent's namespace
       │  stdin / stdout
       │
    Your LLM agent (Claude Code, Codex, etc.) or your own script
```

The two upstreams stay decoupled. Cloak ships a Chromium binary that speaks vanilla CDP; the harness is a CDP client that doesn't know or care whether it's talking to stock Chromium or a patched one. This repo's adapter is the only thing that touches both APIs.

## Requirements

- Python ≥ 3.11 (for browser-harness)
- `uv` for browser-harness install
- `xvfb` for headed-equivalent display on a server
- Linux (tested on Ubuntu 22.04)

## Install

```bash
# 1. CloakBrowser (Python package + stealth Chromium binary auto-download)
python3 -m venv ~/.cloak-harness/venv
~/.cloak-harness/venv/bin/pip install cloakbrowser
~/.cloak-harness/venv/bin/cloakbrowser install

# 2. browser-harness
git clone https://github.com/browser-use/browser-harness ~/Developer/browser-harness
cd ~/Developer/browser-harness
uv tool install -e .

# 3. This repo
git clone https://github.com/YSKM523/cloak-harness ~/Developer/cloak-harness

# 4. Point browser-harness at our agent_helpers.py
mkdir -p ~/Developer/browser-harness/agent-workspace
ln -sf ~/Developer/cloak-harness/agent-workspace/agent_helpers.py \
       ~/Developer/browser-harness/agent-workspace/agent_helpers.py

# 5. Tell agent_helpers.py where cloak lives
export CLOAK_SITE_PACKAGES=~/.cloak-harness/venv/lib/python3.11/site-packages
```

The launch scripts also use the same venv automatically when resolving the
CloakBrowser binary. If you installed CloakBrowser somewhere else, set
`CLOAK_PYTHON=/path/to/python` or `CLOAK_BIN=/path/to/chrome`.

## Quick start

Two-terminal flow:

```bash
# Terminal 1 — launch stealth Chromium
~/Developer/cloak-harness/scripts/start-cloak.sh

# Terminal 2 — drive it via harness
export BU_CDP_URL=http://127.0.0.1:9222
browser-harness -c '
  goto_url("https://example.com")
  wait_for_load()
  human_click_at_xy(200, 300)
  human_type_text("hello@example.com")
  human_scroll_into_view_selector("#footer")
  print(page_info())
'
```

## Examples

Two scrapers against the same target (Home Depot Canada, 2x4 lumber), showing the two main approaches:

| Example | Approach | When to use |
|---|---|---|
| [`examples/homedepot_lumber.py`](examples/homedepot_lumber.py) | innerText parsing | Quick prototyping; sites without obvious JSON APIs |
| [`examples/homedepot_lumber_api.py`](examples/homedepot_lumber_api.py) | Direct JSON API via `page_fetch_json` | Production scraping. ~10-50x faster, structured data, redesign-proof |
| [`examples/api_discovery.py`](examples/api_discovery.py) | Full discovery workflow — recorder → GraphQL detection → signing detection → schema inference → paginate | Mapping a new target site end-to-end |

![api discovery demo](docs/media/api-discovery.gif)

*Output of `examples/api_discovery.py` against Home Depot Canada: warms session, dumps captured JSON endpoints, runs GraphQL + signing detection, sketches response schema, and paginates the discovered search API to collect 60 products.*

The API approach uses these helpers from `agent_helpers.py`:

- `install_xhr_recorder()` + `recorded_requests()` — capture every fetch/XHR (incl. request bodies)
- `page_fetch_json()` — replay any endpoint from inside the validated browser session
- `detect_graphql()` — surface GraphQL ops with full query, variables, persisted hash
- `detect_signed_requests()` — flag endpoints carrying signature/token params
- `paginate_api()` — loop a paginated endpoint with backoff and per-page callback
- `infer_schema()` — type-sketch a JSON sample to map response shape

See [`docs/reverse-engineering.md`](docs/reverse-engineering.md) for the methodology and full replay snippets (including GraphQL persisted-query replay).

## Personas

Run multiple identities side by side. Each persona has its own profile (cookies, localStorage, IndexedDB) and a stable fingerprint seed reused across launches:

```bash
./scripts/start-cloak.sh                       # default persona
./scripts/start-cloak.sh --persona alice       # named persona
PERSONA=alice ./scripts/start-cloak.sh         # same
./scripts/start-with-proxy.sh 0 --persona alice # proxy session with same persona
```

Profiles live under `~/.cloak-harness/personas/<name>/`. The fingerprint seed is generated once per persona and reused, so the same persona always looks like the same machine. Combined with cookie persistence, this drops anti-bot scoring noticeably on returning visits.

## Captcha solver fallback

When a target shows a visible challenge widget (Turnstile / reCAPTCHA), hand it off to a commercial solver via the `solve_and_inject()` helper:

```python
import os
widget = find_captcha_widget()
if widget:
    token = solve_and_inject(os.environ["CAPSOLVER_KEY"])  # or TWOCAPTCHA_KEY
```

Supports CapSolver and 2Captcha out of the box. Pricing is typically ~$2 per 1000 challenges. See [`examples/session_with_captcha.py`](examples/session_with_captcha.py) for the full pattern (persona + session reuse + captcha fallback + `cf_clearance` extraction for non-browser HTTP follow-up).

## Audit your stack — `cloak-harness doctor`

Before shipping a scraper, check your stealth stack for leaks:

```bash
./scripts/doctor.sh > audit-report.md
```

Probes: `navigator.webdriver` value AND key existence, UA / platform consistency, `window.chrome` presence, plugins/cores/memory plausibility, WebGL renderer, egress IP geolocation vs browser timezone, bot.incolumitas.com (37 vectors), BrowserScan, and produces a markdown report grouped by section with remediation hints.

![doctor demo](docs/media/doctor.gif)

*Sample output: 2 detected leaks (the upstream cloak `'webdriver' in navigator` key residual, and an `America/Toronto` vs `UTC` timezone mismatch — fixable via `cdp('Emulation.setTimezoneOverride', ...)`).*

Run either:

```bash
export BU_CDP_URL=http://127.0.0.1:9222
browser-harness -c "$(cat examples/homedepot_lumber_api.py)"
```

## With a residential proxy

```bash
# Put your proxies in proxies.txt (gitignored), one per line in host:port:user:pass form
cp proxies.txt.example proxies.txt
$EDITOR proxies.txt

# Launch with the first proxy
./scripts/start-with-proxy.sh 0

# Or launch with a named persona, preserving the same profile and fingerprint
./scripts/start-with-proxy.sh 0 --persona alice
```

The forwarder script translates Chromium's inline-auth-incapable `--proxy-server` flag into a clean local hop that handles Basic auth upstream. Useful for any HTTP/HTTPS proxy provider that requires user:pass auth.

## Tested results

See `docs/results.md` for the full table. Quick summary:

| Target | Result |
|---|---|
| `nowsecure.nl` (Cloudflare Turnstile + JS challenge) | ✅ Passes in <1s |
| `bot.incolumitas.com` (37-test comprehensive suite) | ✅ 36/37 (one upstream cloak bug — see `docs/known-issues.md`) |
| BrowserScan bot-detection (30+ vectors) | ✅ All "Normal" |
| Major retailer Akamai Bot Manager (e.g. Home Depot) | ✅ Scrapes search results without challenge |
| `turnstile.zeroclover.io` (Cloudflare "Managed Challenge" / Under Attack) | ❌ Does not pass with or without residential proxy |

What this stack does NOT solve: TLS/JA3 fingerprint, HTTP/2 fingerprint, IP reputation, server-side behavioral history. See `docs/results.md#limitations`.

## Configuration

Environment variables read by the scripts and helpers:

| Variable | Default | Purpose |
|---|---|---|
| `CDP_PORT` | `9222` | Chromium DevTools port |
| `CLOAK_BIN` | resolved from `cloakbrowser.binary_info()` | Override path to cloak Chromium binary |
| `CLOAK_PYTHON` | `~/.cloak-harness/venv/bin/python`, then `python3` | Python interpreter used to import `cloakbrowser` and resolve `CLOAK_BIN` |
| `CLOAK_SITE_PACKAGES` | _unset_ | Path to a venv site-packages where `cloakbrowser` is importable (used by `agent_helpers.py`) |
| `PERSONA` | `default` | Persona name used by launch scripts when `--persona` is not passed |
| `PROFILE` | `~/.cloak-harness/personas/<persona>/profile` | Persistent user-data-dir |
| `FINGERPRINT` | generated once per persona | Cloak's fingerprint seed; reused from the persona fingerprint file |
| `FINGERPRINT_PLATFORM` | `windows` | Platform that cloak should mimic |
| `LOCAL_PORT` | `18888` | Local proxy forwarder bind port |
| `PROXIES_FILE` | `./proxies.txt` | Proxy list path |

## Files

```
cloak-harness/
├── README.md
├── LICENSE                          # MIT
├── proxies.txt.example
├── scripts/
│   ├── start-cloak.sh               # launch stealth Chromium (no proxy)
│   ├── start-with-proxy.sh          # launch stealth Chromium through proxy
│   └── proxy-forwarder.py           # upstream-auth CONNECT forwarder
├── agent-workspace/
│   └── agent_helpers.py             # the integration glue and helper API
└── docs/
    ├── results.md                   # benchmark results
    └── known-issues.md              # upstream bugs + workarounds
```

## Upstream credit

This repo is glue. The actual stealth and agent loop come from:

- **CloakBrowser** (https://github.com/CloakHQ/CloakBrowser) — the C++-patched Chromium binary, the `humanize` algorithms, and the `cloakbrowser.human` module. All "passes detection" credit belongs here.
- **browser-harness** (https://github.com/browser-use/browser-harness) — the daemon, CDP wrapper, agent loop, and `agent-workspace/agent_helpers.py` extension mechanism that lets this repo plug in. All "agent self-evolution" credit belongs here.

Please ⭐ the upstreams. They did the hard work.

## License

MIT — see `LICENSE`.
