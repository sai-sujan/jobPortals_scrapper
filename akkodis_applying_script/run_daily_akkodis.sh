#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${0}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

/opt/anaconda3/bin/python akkodis_applying_script/akkodis_scraper.py \
  --posted-within-days "${AKKODIS_POSTED_WITHIN_DAYS:-4}" \
  --min-hourly-rate "${AKKODIS_MIN_HOURLY_RATE:-55}" \
  --sleep "${AKKODIS_SLEEP:-0.2}"
