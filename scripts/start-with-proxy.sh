#!/usr/bin/env bash
# Launch CloakBrowser through a local upstream-auth forwarder that handles
# Basic auth for HTTP proxies that require credentials.
#
# Usage:
#   ./start-with-proxy.sh <session-index>
#   ./start-with-proxy.sh <session-index> --persona alice
#   PERSONA=alice ./start-with-proxy.sh <session-index>
#
# Reads proxies from $PROXIES_FILE (default: ./proxies.txt) in the format:
#   host:port:user:pass
# one per line. Picks line N (0-indexed).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IDX=0
PERSONA=${PERSONA:-default}
while [[ $# -gt 0 ]]; do
    case "$1" in
        --persona)
            PERSONA=${2:?Missing value for --persona}
            shift 2
            ;;
        --persona=*)
            PERSONA="${1#*=}"
            shift
            ;;
        *)
            IDX=$1
            shift
            ;;
    esac
done

PROXIES_FILE=${PROXIES_FILE:-"$REPO_DIR/proxies.txt"}
LOCAL_PORT=${LOCAL_PORT:-18888}
CDP_PORT=${CDP_PORT:-9222}
PERSONA_DIR="$HOME/.cloak-harness/personas/$PERSONA"
PROFILE=${PROFILE:-"$PERSONA_DIR/profile"}
FINGERPRINT_FILE="$PERSONA_DIR/fingerprint"
FINGERPRINT_PLATFORM=${FINGERPRINT_PLATFORM:-windows}

if [[ ! -f "$PROXIES_FILE" ]]; then
    echo "Missing $PROXIES_FILE. Copy proxies.txt.example and fill in your creds." >&2
    exit 1
fi

PROXY_LINE=$(sed -n "$((IDX + 1))p" "$PROXIES_FILE")
if [[ -z "$PROXY_LINE" ]]; then
    echo "No proxy on line $((IDX + 1)) of $PROXIES_FILE" >&2
    exit 1
fi
IFS=':' read -r PHOST PPORT PUSER PPASS <<< "$PROXY_LINE"

mkdir -p "$PROFILE"

# Stable fingerprint per persona, matching scripts/start-cloak.sh.
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

echo "[cloak-harness] persona: $PERSONA"
echo "[cloak-harness] proxy session #$IDX → $PHOST:$PPORT as $PUSER"
echo "[cloak-harness] binary: $BIN"
echo "[cloak-harness] CDP: 127.0.0.1:$CDP_PORT"
echo "[cloak-harness] profile: $PROFILE"
echo "[cloak-harness] fingerprint: $FINGERPRINT (stable for this persona)"
echo "[cloak-harness] starting local forwarder on 127.0.0.1:$LOCAL_PORT"
PROXIES_FILE="$PROXIES_FILE" python3 \
    "$REPO_DIR/scripts/proxy-forwarder.py" "$IDX" "$LOCAL_PORT" \
    > /tmp/cloak-harness-forwarder.log 2>&1 &
FORWARDER_PID=$!
echo "[cloak-harness] forwarder pid=$FORWARDER_PID"
trap "kill $FORWARDER_PID 2>/dev/null || true" EXIT
sleep 1

echo "[cloak-harness] starting stealth Chromium with proxy"
ARGS=(
    --no-sandbox
    --fingerprint="$FINGERPRINT"
    --fingerprint-platform="$FINGERPRINT_PLATFORM"
    --ignore-gpu-blocklist
    --proxy-server="http://127.0.0.1:$LOCAL_PORT"
    --remote-debugging-port="$CDP_PORT"
    --remote-debugging-address=127.0.0.1
    --user-data-dir="$PROFILE"
    --window-size=1920,1080
)

xvfb-run -a -s "-screen 0 1920x1080x24" "$BIN" "${ARGS[@]}"
