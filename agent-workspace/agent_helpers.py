"""Browser-harness agent helpers that route cloakbrowser's human-like input
through the harness CDP path.

Exposed to browser-harness agents:
    human_click_at_xy(x, y, is_input=False)
    human_move_to(x, y)
    human_type_text(text)
    human_scroll_into_view_selector(selector)
    cursor_pos()

Requires:
    - cloakbrowser installed (`pip install cloakbrowser`)
    - CLOAK_SITE_PACKAGES env var pointing to the venv that has cloakbrowser,
      or cloakbrowser importable from the harness's own Python environment.
"""

import os
import sys
import random

_CLOAK_SITE = os.environ.get("CLOAK_SITE_PACKAGES", "")
if _CLOAK_SITE and os.path.isdir(_CLOAK_SITE) and _CLOAK_SITE not in sys.path:
    sys.path.append(_CLOAK_SITE)

try:
    from cloakbrowser.human import (
        HumanConfig, human_move, human_click,
        human_type, human_scroll_into_view,
    )
    _HUMAN_OK = True
    _HUMAN_ERR = None
except Exception as _e:
    _HUMAN_OK = False
    _HUMAN_ERR = _e


_cursor = {"x": None, "y": None}
_CFG = HumanConfig() if _HUMAN_OK else None


class _HarnessRawMouse:
    """Implements cloakbrowser.human.RawMouse against browser-harness CDP."""

    def __init__(self):
        self._down = False
        self._button = "left"

    def _cdp(self, **kw):
        from browser_harness.helpers import cdp
        return cdp("Input.dispatchMouseEvent", **kw)

    def move(self, x, y):
        self._cdp(
            type="mouseMoved",
            x=float(x), y=float(y),
            button=(self._button if self._down else "none"),
            buttons=(1 if self._down else 0),
        )
        _cursor["x"] = float(x)
        _cursor["y"] = float(y)

    def down(self):
        self._down = True
        self._cdp(
            type="mousePressed",
            x=_cursor["x"] or 0.0, y=_cursor["y"] or 0.0,
            button=self._button, buttons=1, clickCount=1,
        )

    def up(self):
        self._down = False
        self._cdp(
            type="mouseReleased",
            x=_cursor["x"] or 0.0, y=_cursor["y"] or 0.0,
            button=self._button, buttons=0, clickCount=1,
        )

    def wheel(self, dx, dy):
        self._cdp(
            type="mouseWheel",
            x=_cursor["x"] or 0.0, y=_cursor["y"] or 0.0,
            deltaX=float(dx), deltaY=float(dy),
        )


def _ensure_initial_cursor():
    if _cursor["x"] is not None:
        return
    lo_x, hi_x = _CFG.initial_cursor_x
    lo_y, hi_y = _CFG.initial_cursor_y
    _cursor["x"] = random.uniform(lo_x, hi_x)
    _cursor["y"] = random.uniform(lo_y, hi_y)


def human_click_at_xy(x, y, is_input=False, cfg=None):
    """Click at (x, y) using cloak's human-like Bezier trajectory + aim/hold delays."""
    if not _HUMAN_OK:
        raise RuntimeError(f"cloakbrowser.human unavailable: {_HUMAN_ERR}")
    cfg = cfg or _CFG
    _ensure_initial_cursor()
    raw = _HarnessRawMouse()
    human_move(raw, _cursor["x"], _cursor["y"], float(x), float(y), cfg)
    human_click(raw, is_input, cfg)


def human_move_to(x, y, cfg=None):
    """Move the cursor to (x, y) using a human-like trajectory, without clicking."""
    if not _HUMAN_OK:
        raise RuntimeError(f"cloakbrowser.human unavailable: {_HUMAN_ERR}")
    cfg = cfg or _CFG
    _ensure_initial_cursor()
    raw = _HarnessRawMouse()
    human_move(raw, _cursor["x"], _cursor["y"], float(x), float(y), cfg)


def cursor_pos():
    """Return current tracked cursor position, or None if no move has happened."""
    if _cursor["x"] is None:
        return None
    return (_cursor["x"], _cursor["y"])


_MODIFIER_BITS = {"Shift": 8, "Control": 2, "Ctrl": 2, "Meta": 4, "Cmd": 4, "Alt": 1}

_NAMED_KEYS = {
    "Enter": (13, "Enter", "\r"),
    "Tab": (9, "Tab", "\t"),
    "Backspace": (8, "Backspace", ""),
    "Escape": (27, "Escape", ""),
    "Delete": (46, "Delete", ""),
    " ": (32, "Space", " "),
    "Shift": (16, "ShiftLeft", ""),
    "Control": (17, "ControlLeft", ""),
    "Meta": (91, "MetaLeft", ""),
    "Alt": (18, "AltLeft", ""),
}


def _key_info(key):
    if key in _NAMED_KEYS:
        return _NAMED_KEYS[key]
    if len(key) == 1:
        ch = key
        if ch.isalpha():
            return (ord(ch.upper()), f"Key{ch.upper()}", ch)
        if ch.isdigit():
            return (ord(ch), f"Digit{ch}", ch)
        return (ord(ch) if ord(ch) < 256 else 0, "", ch)
    return (0, key, "")


class _HarnessRawKeyboard:
    """Implements cloakbrowser.human.RawKeyboard against browser-harness CDP."""

    def __init__(self):
        self._modifiers = 0

    def _cdp(self, **kw):
        from browser_harness.helpers import cdp
        return cdp("Input.dispatchKeyEvent", **kw)

    def down(self, key):
        mb = _MODIFIER_BITS.get(key, 0)
        if mb:
            self._modifiers |= mb
            vk, code, _ = _NAMED_KEYS[key]
            self._cdp(
                type="keyDown", key=key, code=code,
                windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk,
                modifiers=self._modifiers,
            )
            return
        vk, code, text = _key_info(key)
        base = dict(key=key, code=code, modifiers=self._modifiers,
                    windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)
        # keyDown without text — the separate char event is what inserts the
        # character. Including text in both causes double-insertion.
        self._cdp(type="keyDown", **base)
        if text and len(text) == 1:
            self._cdp(type="char", text=text, **base)

    def up(self, key):
        mb = _MODIFIER_BITS.get(key, 0)
        if mb:
            self._modifiers &= ~mb
            vk, code, _ = _NAMED_KEYS[key]
            self._cdp(
                type="keyUp", key=key, code=code,
                windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk,
                modifiers=self._modifiers,
            )
            return
        vk, code, _ = _key_info(key)
        self._cdp(
            type="keyUp", key=key, code=code,
            windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk,
            modifiers=self._modifiers,
        )

    def type(self, text):
        from browser_harness.helpers import cdp
        cdp("Input.insertText", text=text)

    def insert_text(self, text):
        from browser_harness.helpers import cdp
        cdp("Input.insertText", text=text)


class _HarnessCdpSession:
    """Shim matching cloak's cdp_session.send(method, params) signature."""

    def send(self, method, params=None):
        from browser_harness.helpers import cdp
        return cdp(method, **(params or {}))


def human_type_text(text, cfg=None):
    """Type ``text`` with human per-character timing, occasional mistypes,
    natural shift handling, and isTrusted=true key events via CDP.

    Caller must already have focused the target input (e.g. via
    human_click_at_xy on the field first).
    """
    if not _HUMAN_OK:
        raise RuntimeError(f"cloakbrowser.human unavailable: {_HUMAN_ERR}")
    cfg = cfg or _CFG
    raw = _HarnessRawKeyboard()
    human_type(page=None, raw=raw, text=text, cfg=cfg, cdp_session=_HarnessCdpSession())


class _HarnessPage:
    """Minimal page-like object exposing only what cloak.human.scroll needs."""

    @property
    def viewport_size(self):
        from browser_harness.helpers import js
        w = js("return window.innerWidth")
        h = js("return window.innerHeight")
        return {"width": int(w), "height": int(h)}


def _bounding_box(selector):
    from browser_harness.helpers import js
    expr = (
        "const el = document.querySelector(" + repr(selector) + ");"
        "if (!el) return null;"
        "const r = el.getBoundingClientRect();"
        "return {x: r.x, y: r.y, width: r.width, height: r.height};"
    )
    return js(expr)


def install_xhr_recorder():
    """Inject a fetch + XMLHttpRequest interceptor that survives navigations
    and accumulates `window._req` with one entry per request.

    Each entry has: {t, url, method, status, ct, bodyHead, xhr?}.
    `bodyHead` is the first 600 chars of the response body (text/JSON only).

    Use to reverse-engineer a site's hidden JSON APIs before scripting them
    directly. Typical flow:
        install_xhr_recorder()
        goto_url("https://target/...")
        wait(5)
        observed = recorded_requests()
        # inspect, then call the discovered endpoint via page_fetch_json()
    """
    from browser_harness.helpers import cdp
    cdp("Page.addScriptToEvaluateOnNewDocument", source="""
        window._req = window._req || [];
        if (!window._fetchHooked) {
            window._fetchHooked = true;
            const origFetch = window.fetch;
            window.fetch = async function(...args) {
                const url = typeof args[0] === 'string' ? args[0] : args[0].url;
                const opts = args[1] || {};
                const t = performance.now();
                try {
                    const r = await origFetch.apply(this, args);
                    const ct = r.headers.get('content-type') || '';
                    let bodyHead = '';
                    if (ct.includes('json') || ct.includes('text')) {
                        try { bodyHead = (await r.clone().text()).slice(0, 600); } catch(e) {}
                    }
                    window._req.push({t: Math.round(t), url, method: opts.method||'GET', status: r.status, ct, bodyHead});
                    return r;
                } catch(e) {
                    window._req.push({t: Math.round(t), url, method: opts.method||'GET', status: 'ERR', error: String(e)});
                    throw e;
                }
            };
            const origOpen = XMLHttpRequest.prototype.open;
            const origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(method, url) { this._url=url; this._method=method; return origOpen.apply(this, arguments); };
            XMLHttpRequest.prototype.send = function() {
                this.addEventListener('load', () => {
                    let bodyHead = '';
                    try { bodyHead = (this.responseText || '').slice(0, 600); } catch(e) {}
                    window._req.push({t: Math.round(performance.now()), url: this._url, method: this._method, status: this.status, ct: this.getResponseHeader('content-type')||'', bodyHead, xhr: true});
                });
                return origSend.apply(this, arguments);
            };
        }
    """)


def recorded_requests(only_json=False, host_substr=None):
    """Return the list of requests captured since install_xhr_recorder().

    Args:
        only_json: If True, return only responses whose content-type contains
            "json" or whose body starts with "{" or "[".
        host_substr: If set, filter to URLs containing this substring.
    """
    from browser_harness.helpers import js
    import json as _json
    raw = js("return JSON.stringify(window._req || [])")
    reqs = _json.loads(raw) if raw else []
    if host_substr:
        reqs = [r for r in reqs if host_substr in r.get("url", "")]
    if only_json:
        reqs = [
            r for r in reqs
            if "json" in r.get("ct", "").lower()
            or r.get("bodyHead", "").startswith("{")
            or r.get("bodyHead", "").startswith("[")
        ]
    return reqs


def page_fetch_json(url, headers=None, method="GET", body=None):
    """Call ``url`` from within the active page's JS context, returning the
    parsed JSON. Cookies, CF clearance, CSRF tokens, and same-origin auth
    headers all attach automatically — this is the right primitive for hitting
    site APIs once the browser has past their anti-bot layer.
    """
    from browser_harness.helpers import js
    import json as _json
    opts = {"method": method, "headers": {"accept": "application/json", **(headers or {})}}
    if body is not None:
        opts["body"] = body if isinstance(body, str) else _json.dumps(body)
    opts_js = _json.dumps(opts)
    expr = (
        "return fetch(" + _json.dumps(url) + ", " + opts_js + ")"
        ".then(r => r.text())"
        ".then(t => { try { return JSON.parse(t); } catch(e) { return {__raw: t}; } });"
    )
    return js(expr)


def human_scroll_into_view_selector(selector, cfg=None):
    """Scroll ``selector`` into view using cloak's accelerate/cruise/decelerate
    wheel pattern. Returns the final bounding box and updates cursor position.
    """
    if not _HUMAN_OK:
        raise RuntimeError(f"cloakbrowser.human unavailable: {_HUMAN_ERR}")
    cfg = cfg or _CFG
    _ensure_initial_cursor()
    raw = _HarnessRawMouse()
    page = _HarnessPage()
    get_box = lambda: _bounding_box(selector)
    box, cx, cy = human_scroll_into_view(
        page, raw, get_box, _cursor["x"], _cursor["y"], cfg,
    )
    _cursor["x"], _cursor["y"] = cx, cy
    return box
