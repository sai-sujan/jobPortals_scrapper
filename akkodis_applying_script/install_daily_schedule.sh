#!/bin/zsh
set -euo pipefail

PLIST_NAME="com.venkata.akkodis-daily.plist"
SCRIPT_DIR="$(cd "$(dirname "${0}")" && pwd)"
SOURCE="${SCRIPT_DIR}/${PLIST_NAME}"
TARGET="${HOME}/Library/LaunchAgents/${PLIST_NAME}"

mkdir -p "${HOME}/Library/LaunchAgents"
cp "${SOURCE}" "${TARGET}"

launchctl unload "${TARGET}" 2>/dev/null || true
launchctl load "${TARGET}"

echo "Installed Akkodis daily scraper schedule."
echo "It will run every day at 8:00 AM and write Excel files to:"
echo "${SCRIPT_DIR}/output"
