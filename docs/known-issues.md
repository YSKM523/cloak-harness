# Known issues and notes

## 1. `'webdriver' in navigator` key remains true (upstream CloakBrowser)

**Where**: CloakBrowser 0.3.28, Chromium 146.0.7680.177.

**Observed**:

```js
navigator.webdriver       // false  ← value is patched
'webdriver' in navigator  // true   ← key still exists on Navigator.prototype
```

**Impact**: fpscanner's `WEBDRIVER` check tests key existence (not value) and fails. Detectable by any fingerprinter using `in` operator or `hasOwnProperty`.

**Workaround** (script-side patch, applied at every new document):

```python
cdp("Page.addScriptToEvaluateOnNewDocument", source="""
  (function() {
    const p = Object.getPrototypeOf(navigator);
    if (p && Object.getOwnPropertyDescriptor(p, 'webdriver')) {
      delete p.webdriver;
    }
  })();
""")
```

This is not a complete fix — a determined fingerprinter can detect that the descriptor was removed, but it covers the common `in` operator check.

## 2. `keyDown text + char event` double-insertion in `browser-harness.press_key`

**Where**: browser-harness `src/browser_harness/helpers.py:222-224`.

**Observed**: The harness's `press_key` emits both:

```python
cdp("Input.dispatchKeyEvent", type="keyDown", text=text, ...)
cdp("Input.dispatchKeyEvent", type="char", text=text, ...)
```

Chromium's CDP inserts the character once per event that carries `text`, so the character ends up in the focused field twice (e.g., typing space becomes two spaces).

**Impact**: Limited in normal use of `press_key` since most calls are for special keys (Enter/Tab/Arrows) where the inserted "text" is invisible (`\r`, `\t`, `""`). But space and Enter-in-textarea both double.

**Workaround used in this repo's `agent_helpers.py`**: emit `text` only in the `char` event, not in `keyDown`. See `_HarnessRawKeyboard.down`.

## 3. Default timezone leak

CloakBrowser respects the process `TZ` environment variable and `--timezone` flag, but the default is the host's system timezone (often `UTC` on cloud servers). A Windows-impersonating UA reporting `UTC` is a strong tell.

**Workarounds, in order of preference**:

1. Per-session via CDP after launch:
   ```python
   cdp("Emulation.setTimezoneOverride", timezoneId="America/New_York")
   cdp("Emulation.setLocaleOverride", locale="en-US")
   ```
2. Set `TZ` env var before launching:
   ```bash
   TZ=America/New_York ./scripts/start-cloak.sh
   ```
3. Use cloak's geoip extra (`pip install cloakbrowser[geoip]`) which auto-resolves timezone from proxy egress IP.

## 4. Linux server detection vectors

Running CloakBrowser on a Linux server (no real display) requires `--no-sandbox` and `xvfb-run`. Several side effects:

- `chrome://gpu` shows software rasterizer information that differs from a real Windows GPU stack (cloak partially mitigates with `--fingerprint-platform=windows`).
- Audio output devices are absent; some fingerprinters check `navigator.mediaDevices.enumerateDevices()` for the expected audio output category.
- Font rendering uses fontconfig/freetype rather than DirectWrite; canvas font metrics differ.

None of these are fatal individually but they accumulate. Headed-mode-on-real-Windows would score higher.
