#!/usr/bin/env bash
# Launch a CloakBrowser stealth Chromium with CDP exposed on :9222.
# Uses xvfb for a headed-equivalent display on a server without a real monitor.
set -euo pipefail

CDP_PORT=${CDP_PORT:-9222}
PROFILE=${PROFILE:-$HOME/.cloak-harness/profile}
FINGERPRINT=${FINGERPRINT:-$((RANDOM % 99999))}
FINGERPRINT_PLATFORM=${FINGERPRINT_PLATFORM:-windows}

# Resolve the cloak Chromium binary path
if [[ -n "${CLOAK_BIN:-}" ]]; then
    BIN="$CLOAK_BIN"
else
    BIN=$(python3 -c "from cloakbrowser import binary_info; print(binary_info()['binary_path'])")
fi

mkdir -p "$PROFILE"

ARGS=(
    --no-sandbox
    --fingerprint="$FINGERPRINT"
    --fingerprint-platform="$FINGERPRINT_PLATFORM"
    --ignore-gpu-blocklist
    --remote-debugging-port="$CDP_PORT"
    --remote-debugging-address=127.0.0.1
    --user-data-dir="$PROFILE"
    --window-size=1920,1080
)

echo "[cloak-harness] binary: $BIN"
echo "[cloak-harness] CDP: 127.0.0.1:$CDP_PORT"
echo "[cloak-harness] profile: $PROFILE"
echo "[cloak-harness] fingerprint=$FINGERPRINT platform=$FINGERPRINT_PLATFORM"

exec xvfb-run -a -s "-screen 0 1920x1080x24" "$BIN" "${ARGS[@]}"
