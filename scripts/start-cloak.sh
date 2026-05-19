#!/usr/bin/env bash
# Launch a CloakBrowser stealth Chromium with CDP exposed on :9222.
# Uses xvfb for a headed-equivalent display on a server without a real monitor.
#
# Usage:
#   ./start-cloak.sh                       # default persona
#   ./start-cloak.sh --persona alice       # named persona (own profile + fingerprint)
#   PERSONA=alice ./start-cloak.sh         # same
#
# Personas isolate cookies, localStorage, IndexedDB, and the per-launch
# fingerprint seed. Reusing the same persona across runs preserves the
# "this user has been here before" signal, which lowers anti-bot scoring
# on most sites.
set -euo pipefail

PERSONA=${PERSONA:-default}
if [[ "${1:-}" == "--persona" && -n "${2:-}" ]]; then
    PERSONA=$2
fi

CDP_PORT=${CDP_PORT:-9222}
PERSONA_DIR="$HOME/.cloak-harness/personas/$PERSONA"
PROFILE=${PROFILE:-"$PERSONA_DIR/profile"}
FINGERPRINT_FILE="$PERSONA_DIR/fingerprint"
FINGERPRINT_PLATFORM=${FINGERPRINT_PLATFORM:-windows}

mkdir -p "$PROFILE"

# Stable fingerprint per persona — generated once, reused on subsequent
# launches so the same persona always looks like the same machine.
if [[ -f "$FINGERPRINT_FILE" ]]; then
    FINGERPRINT=$(cat "$FINGERPRINT_FILE")
else
    FINGERPRINT=${FINGERPRINT:-$((RANDOM % 99999))}
    echo "$FINGERPRINT" > "$FINGERPRINT_FILE"
fi

if [[ -n "${CLOAK_BIN:-}" ]]; then
    BIN="$CLOAK_BIN"
else
    if [[ -n "${CLOAK_PYTHON:-}" ]]; then
        PY="$CLOAK_PYTHON"
    elif [[ -x "$HOME/.cloak-harness/venv/bin/python" ]]; then
        PY="$HOME/.cloak-harness/venv/bin/python"
    else
        PY="$(command -v python3)"
    fi
    if ! BIN=$("$PY" -c "from cloakbrowser import binary_info; print(binary_info()['binary_path'])"); then
        echo "Could not import cloakbrowser with $PY." >&2
        echo "Install it via ~/.cloak-harness/venv/bin/pip install cloakbrowser, set CLOAK_PYTHON, or set CLOAK_BIN." >&2
        exit 1
    fi
fi

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

echo "[cloak-harness] persona: $PERSONA"
echo "[cloak-harness] binary: $BIN"
echo "[cloak-harness] CDP: 127.0.0.1:$CDP_PORT"
echo "[cloak-harness] profile: $PROFILE"
echo "[cloak-harness] fingerprint: $FINGERPRINT (stable for this persona)"

exec xvfb-run -a -s "-screen 0 1920x1080x24" "$BIN" "${ARGS[@]}"
