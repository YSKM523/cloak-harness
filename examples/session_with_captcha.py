"""Example: persona-based session reuse with captcha-solver fallback.

Demonstrates the three "production-readiness" pieces:

    1. Persona — launched via ``./scripts/start-cloak.sh --persona <name>``,
       same persona always uses the same profile + fingerprint, so cookies
       and "this user has been here" signals accumulate.
    2. Session persistence — save_session() / load_session() let you carry
       cookies + localStorage between scrapes without keeping the browser
       running.
    3. Captcha fallback — if a Turnstile / reCAPTCHA widget appears, hand
       it to a solver service (CapSolver or 2Captcha) and inject the token.

The script is idempotent: on first run it builds the session; on
subsequent runs it reuses cookies and likely skips the challenge entirely.

Run via:
    export BU_CDP_URL=http://127.0.0.1:9222
    export CAPSOLVER_KEY=...  # optional; only needed if a widget appears
    browser-harness -c "$(cat examples/session_with_captcha.py)"
"""

import os
import time

TARGET = "https://nowsecure.nl/"
SESSION_FILE = os.path.expanduser("~/.cloak-harness/sessions/nowsecure.json")

os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)


# 1. Restore prior session if we have one (cookies + localStorage).
if os.path.exists(SESSION_FILE):
    print(f"loading session from {SESSION_FILE}")
    # Cookies have to be set BEFORE navigating; load_session does both
    # cookies (CDP-side) and localStorage (after navigation).
    import json as _j
    with open(SESSION_FILE) as f:
        saved = _j.load(f)
    import_cookies(saved.get("cookies") or [])
else:
    print("no prior session — fresh start")


# 2. Navigate to the target.
print(f"navigating to {TARGET}")
goto_url(TARGET)
wait_for_load(timeout=30)
time.sleep(3)


# 3. If a challenge appears, hand it to the solver service.
widget = find_captcha_widget()
if widget:
    api_key = os.environ.get("CAPSOLVER_KEY") or os.environ.get("TWOCAPTCHA_KEY")
    if not api_key:
        print(f"⚠ captcha widget detected ({widget['type']}, sitekey={widget['sitekey'][:20]}...)")
        print("  set CAPSOLVER_KEY or TWOCAPTCHA_KEY env var to auto-solve")
    else:
        provider = "capsolver" if "CAPSOLVER_KEY" in os.environ else "2captcha"
        print(f"solving {widget['type']} via {provider} ...")
        t0 = time.time()
        token = solve_and_inject(api_key, provider=provider)
        print(f"  solved in {time.time()-t0:.1f}s, token length {len(token) if token else 0}")
        time.sleep(2)
        wait_for_load(timeout=15)
else:
    print("no captcha widget — direct access")


# 4. Confirm we landed on real content (not a challenge interstitial).
info = page_info()
title = info.get("title", "")
print(f"\nfinal URL: {info['url']}")
print(f"final title: {title!r}")

if "moment" in title.lower() or "just" in title.lower():
    print("⚠ still on challenge page — solver may have failed")
else:
    print(f"✓ on real content")


# 5. Save the session for next time.
print(f"\nsaving session to {SESSION_FILE}")
save_session(SESSION_FILE)


# 6. Extract cf_clearance for use with non-browser HTTP clients.
clearance = get_cf_clearance()
if clearance:
    print(f"\ncf_clearance: {clearance[:60]}... ({len(clearance)} chars)")
    print("  with this cookie + matching UA, you can hit the origin from")
    print("  `requests` / `curl` directly for the next ~30 minutes,")
    print("  no browser needed.")
else:
    print("\n(no cf_clearance cookie set on this origin)")
