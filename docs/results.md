# Benchmark results

All tests run on Linux server with `xvfb-run -screen 0 1920x1080x24` (headed-equivalent via virtual display). Same harness call path for every test. Tested 2026-05-19 against CloakBrowser 0.3.28 (Chromium 146.0.7680.177).

## Bot detection benchmarks

### nowsecure.nl (Cloudflare Turnstile + JS challenge)

✅ **Passed in <1 second**, no interaction needed. Page title goes directly to `nowsecure.nl` with body `NOWSECURE BY NODRIVER`.

### bot.incolumitas.com (37-test comprehensive suite)

✅ **36/37 tests passed.**

| Category | Result |
|---|---|
| `new-tests` (9 checks) | 9/9 OK — puppeteerEvaluationScript, webdriverPresent, connectionRTT, refMatch, overrideTest, overflowTest, puppeteerExtraStealthUsed, inconsistentWebWorker/ServiceWorkerNavigatorProperty |
| `intoli` (6 checks) | 6/6 OK — userAgent, webDriver, webDriverAdvanced, pluginsLength, pluginArray, languages |
| `fpscanner` (22 checks) | 21/22 OK |
| └─ `WEBDRIVER` | ❌ **FAIL** — `'webdriver' in navigator === true` (the key exists on `Navigator.prototype` even though the value is `false`). See [Known issues](#known-issues). |

### BrowserScan bot-detection (30+ vectors)

✅ All categories report **Normal**: WebDriver, Selenium, Puppeteer, NightmareJS, PhantomJS, Webdriverio, Headless Chrome, Coaches, FMiner, Born, Phantomas, Rhino, etc.

### turnstile.zeroclover.io (Cloudflare "Managed Challenge" / Under Attack mode)

❌ **Did not pass** within 40 seconds, with or without residential proxy. Page stays on the "Performing security verification" interstitial; the Turnstile widget runs invisibly and the `cf-chl-widget-*` response token never populates. This is Cloudflare's strictest tier — passing it generally requires more than browser fingerprint and behavior alone (see [Limitations](#limitations)).

## Fingerprint values reported

After launch, the stealth Chromium reports the following to JS-based fingerprinters:

| Property | Value |
|---|---|
| `navigator.webdriver` (value) | `false` |
| `navigator.userAgent` | Windows Chrome 146.0.0.0 |
| `navigator.platform` | `Win32` |
| `navigator.vendor` | `Google Inc.` |
| `navigator.plugins.length` | 5 |
| `navigator.hardwareConcurrency` | 8 |
| `navigator.deviceMemory` | 8 |
| WebGL renderer | Randomized GPU per session (e.g. NVIDIA RTX 3050 / 4060 / 4070) |
| Screen | 1920×1080 @32bit |

Default timezone is `UTC`. Set per-session via CDP `Emulation.setTimezoneOverride` to match your egress IP.

## Human-input verification

Recorded events for `human_click_at_xy(660, 320)`:

| Phase | Detail |
|---|---|
| Intermediate `mousemove` events | 36 along a Bezier curve with wobble |
| Trajectory duration | 581ms |
| Aim delay (last move → `mousedown`) | 122ms |
| Click hold (`mousedown` → `mouseup`) | 141ms |

Recorded events for `human_type_text("Hello World!")`:

| Phase | Detail |
|---|---|
| Total events | 54, all with `isTrusted === true` |
| Inter-keystroke gaps | 36–156 ms range (varies), one 767 ms "thinking pause" |
| Final input value | `Hello World!` (correct, no duplication) |

Recorded events for `human_scroll_into_view_selector("#target")` (target 2999px below viewport):

| Phase | Detail |
|---|---|
| Wheel events | 87 chunks (20–40 px each) |
| Total scroll time | 3380 ms |
| Pattern | accelerate → cruise → decelerate, with optional overshoot + correction |

## Known issues

1. **`'webdriver' in navigator` key leak.** CloakBrowser 0.3.28 sets `navigator.webdriver = false` but does not remove the key from `Navigator.prototype`. fpscanner's `WEBDRIVER` check looks for key existence and fails. Workaround: inject `delete Object.getPrototypeOf(navigator).webdriver` via CDP `Page.addScriptToEvaluateOnNewDocument` at startup. See `docs/known-issues.md` for a deeper note.

2. **Default timezone is UTC.** Disclosed timezone disagrees with most real users' systems and any geo-matching IP. Always override via CDP `Emulation.setTimezoneOverride` to match your egress geography.

3. **`--no-sandbox` is required on Linux servers.** Visible in `chrome://gpu` and detectable by some advanced fingerprinters. No clean workaround for headless server environments without configuring the SUID sandbox.

## Limitations

This stack does not address:

- **TLS/JA3 and HTTP/2 SETTINGS fingerprint.** CloakBrowser modifies the JS/C++ rendering layer, not the network stack. Cloudflare Enterprise plans inspect these.
- **IP reputation.** Residential proxies share their IP pools across many customers; many provider IPs are already on shared blocklists used by major bot-detection services. Proxy provider quality varies considerably.
- **Server-side behavioral fingerprinting** that requires long sessions, account history, or device persistence (e.g., banking, sneaker drops).
- **CAPTCHA solving.** When a visible challenge appears, you need a separate solver service (CapSolver, 2Captcha, etc.) — this stack does not interact with widgets.
