# cloak-harness

A bridge wiring [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) (stealth Chromium binary) and [browser-harness](https://github.com/browser-use/browser-harness) (LLM-driven CDP harness) so they cooperate cleanly: cloak provides the indistinguishable-from-real-Chrome process, browser-harness provides the agent control loop, and this repo adds the glue so cloak's human-like input flows through the harness's CDP path.

![cloak-harness demo](docs/media/demo.gif)

*Form filled by an LLM agent through `browser-harness`, with each keystroke and click going through `cloak`'s human-like input adapter (Bezier mouse trajectory, per-key timing, aim/hold delays). All inside a stealth Chromium that passes most bot-detection benchmarks. See [`docs/results.md`](docs/results.md) for the full table.*

## What this is and isn't

- **Is**: ~250 lines of integration glue (`agent-workspace/agent_helpers.py`), launch scripts (`scripts/`), and a documented setup recipe with honest benchmark results.
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
git clone https://github.com/<you>/cloak-harness ~/Developer/cloak-harness

# 4. Point browser-harness at our agent_helpers.py
mkdir -p ~/Developer/browser-harness/agent-workspace
ln -sf ~/Developer/cloak-harness/agent-workspace/agent_helpers.py \
       ~/Developer/browser-harness/agent-workspace/agent_helpers.py

# 5. Tell agent_helpers.py where cloak lives
export CLOAK_SITE_PACKAGES=~/.cloak-harness/venv/lib/python3.11/site-packages
```

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

The API approach uses the helpers `install_xhr_recorder()` + `recorded_requests()` + `page_fetch_json()` exposed from `agent_helpers.py`. See [`docs/reverse-engineering.md`](docs/reverse-engineering.md) for the methodology of discovering a site's hidden APIs and replaying them through the validated browser session.

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
| `CLOAK_SITE_PACKAGES` | _unset_ | Path to a venv site-packages where `cloakbrowser` is importable (used by `agent_helpers.py`) |
| `PROFILE` | `~/.cloak-harness/profile[-proxy]` | Persistent user-data-dir |
| `FINGERPRINT` | random | Cloak's per-session fingerprint seed |
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
│   └── agent_helpers.py             # the integration glue (~250 lines)
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
