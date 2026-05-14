#!/bin/zsh
set -euo pipefail

TARGET="${HOME}/Library/LaunchAgents/com.venkata.akkodis-daily.plist"

launchctl unload "${TARGET}" 2>/dev/null || true
rm -f "${TARGET}"

echo "Removed Akkodis daily scraper schedule."
