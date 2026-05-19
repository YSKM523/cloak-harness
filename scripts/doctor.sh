#!/usr/bin/env bash
# cloak-harness doctor — audit the running stealth Chromium for leaks.
# Outputs a markdown report to stdout (or to a file via `> report.md`).
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${BU_CDP_URL:-}" ]]; then
    export BU_CDP_URL="http://127.0.0.1:9222"
fi

if ! curl -sf "$BU_CDP_URL/json/version" > /dev/null; then
    echo "No CDP endpoint at $BU_CDP_URL — start a stealth Chromium first via scripts/start-cloak.sh" >&2
    exit 1
fi

exec browser-harness -c "$(cat "$REPO_DIR/scripts/doctor.py")"
