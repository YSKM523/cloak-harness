"""cloak-harness doctor — audit the active stealth Chromium for leaks.

Probes JS-visible fingerprint, runs against public bot-detection benchmarks,
and produces a markdown report. Run via:

    export BU_CDP_URL=http://127.0.0.1:9222
    browser-harness -c "$(cat scripts/doctor.py)" > audit-report.md
"""

import json
import time

REPORT = []


def section(title, *, level=2):
    REPORT.append("")
    REPORT.append(("#" * level) + " " + title)


def line(text):
    REPORT.append(text)


def check(name, ok, detail=""):
    marker = "✓" if ok else "✗"
    suffix = f" — {detail}" if detail else ""
    REPORT.append(f"- {marker} **{name}**{suffix}")


# --- 1. JS fingerprint probes ---------------------------------------------

section("JS-visible fingerprint")

fp = json.loads(js("""
return JSON.stringify({
    ua: navigator.userAgent,
    platform: navigator.platform,
    vendor: navigator.vendor,
    webdriver_value: navigator.webdriver,
    webdriver_key_exists: 'webdriver' in navigator,
    languages: navigator.languages,
    plugins_len: navigator.plugins.length,
    hwc: navigator.hardwareConcurrency,
    mem: navigator.deviceMemory,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    webgl_renderer: (() => { try { const c=document.createElement('canvas').getContext('webgl'); const d=c.getExtension('WEBGL_debug_renderer_info'); return c.getParameter(d.UNMASKED_RENDERER_WEBGL); } catch(e){return 'err'} })(),
    chrome_obj: typeof window.chrome,
    permissions_obj: typeof navigator.permissions,
    screen: screen.width + 'x' + screen.height + '@' + screen.colorDepth + 'bit',
});
"""))

check("`navigator.webdriver === false`", fp["webdriver_value"] is False, f"value: {fp['webdriver_value']}")
check("`'webdriver' in navigator` is false (key removed)",
      not fp["webdriver_key_exists"],
      "key still on prototype — cloak upstream bug, see docs/known-issues.md" if fp["webdriver_key_exists"] else "")
check("UA reports platform consistent with `--fingerprint-platform`",
      "Windows" in fp["ua"] and fp["platform"] == "Win32",
      f"UA: `{fp['ua'][:80]}`, platform: `{fp['platform']}`")
check("`window.chrome` present (real Chrome has this)",
      fp["chrome_obj"] == "object",
      f"typeof window.chrome: {fp['chrome_obj']}")
check("plugins length > 0", fp["plugins_len"] > 0, f"{fp['plugins_len']} plugins")
check("hardware concurrency reasonable (2-32)",
      2 <= fp["hwc"] <= 32, f"{fp['hwc']} cores")

line("")
line(f"  WebGL renderer: `{fp['webgl_renderer'][:120]}`")
line(f"  Screen: `{fp['screen']}`")
line(f"  Languages: `{fp['languages']}`")


# --- 2. Timezone / IP consistency -----------------------------------------

section("Timezone vs egress IP")

try:
    ipdata = page_fetch_json("https://ipinfo.io/json")
    expected_tz = ipdata.get("timezone")
    actual_tz = fp["timezone"]
    line(f"")
    line(f"  Egress IP: `{ipdata.get('ip')}` ({ipdata.get('city')}, {ipdata.get('region')}, {ipdata.get('country')})")
    line(f"  IP-derived timezone: `{expected_tz}`")
    line(f"  Browser timezone: `{actual_tz}`")
    check("Browser timezone matches egress IP geolocation",
          actual_tz == expected_tz,
          f"mismatch — set via `cdp('Emulation.setTimezoneOverride', timezoneId='{expected_tz}')`" if actual_tz != expected_tz else "")
    org = ipdata.get("org", "") or ""
    org_lower = org.lower()
    datacenter_markers = (
        "amazon", "aws", "google", "digitalocean", "microsoft", "azure",
        "oracle", "ovh", "hetzner", "linode", "akamai", "vultr", "choopa",
        "leaseweb", "contabo", "cloudflare", "datacamp", "m247",
        "colo", "colocation", "hosting", "datacenter", "data center",
    )
    obvious_datacenter = any(marker in org_lower for marker in datacenter_markers)
    check("Egress IP is not an obvious datacenter ASN",
          bool(org) and "AS" in org and not obvious_datacenter,
          f"org: `{org or '?'}`")
except Exception as e:
    line(f"  could not reach ipinfo.io: {e}")


# --- 3. bot.incolumitas.com comprehensive suite ---------------------------

section("bot.incolumitas.com (37 vectors)")

goto_url("https://bot.incolumitas.com/")
time.sleep(8)

incolumitas = json.loads(js("""
return JSON.stringify({
    new_tests: document.getElementById('new-tests') && document.getElementById('new-tests').innerText,
    detection_tests: document.getElementById('detection-tests') && document.getElementById('detection-tests').innerText,
});
"""))

passed = failed = 0
fail_names = []
for text in (incolumitas.get("new_tests") or "", incolumitas.get("detection_tests") or ""):
    if not text:
        continue
    for entry in text.split('"'):
        pass
    # Simple parsing of "name": "OK"/"FAIL"
    import re
    for name, verdict in re.findall(r'"([A-Za-z_]+)":\s*"(OK|FAIL)"', text):
        if verdict == "OK":
            passed += 1
        else:
            failed += 1
            fail_names.append(name)

line(f"")
line(f"  passed: {passed} / failed: {failed}")
if fail_names:
    line(f"  failing: " + ", ".join(f"`{n}`" for n in fail_names))


# --- 4. BrowserScan headless test category --------------------------------

section("BrowserScan bot-detection")

goto_url("https://www.browserscan.net/bot-detection")
time.sleep(5)

bs_text = js("return document.body.innerText.slice(0, 3000)")
detected = "detected" in bs_text.lower() and "no bots detected" not in bs_text.lower()
check("BrowserScan reports no bot detection", not detected,
      "see https://www.browserscan.net/bot-detection for current verdict")


# --- final ----------------------------------------------------------------

section("Summary", level=2)
all_ok = sum(1 for l in REPORT if l.startswith("- ✓"))
all_fail = sum(1 for l in REPORT if l.startswith("- ✗"))
line(f"")
line(f"  **{all_ok} passed, {all_fail} failed**")
line(f"")
if all_fail:
    line("Remediation tips for failures are inline above. See `docs/known-issues.md` for upstream-reported issues.")
else:
    line("Stack is clean for the probed vectors. Cloudflare Enterprise Managed Challenge may still block — see `docs/results.md` for what this stack does NOT solve.")

print("# cloak-harness audit report")
print("\n".join(REPORT))
