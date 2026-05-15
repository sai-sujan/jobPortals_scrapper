#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python_bin="${PYTHON:-python3}"
venv_dir="${VENV:-.venv}"

"$python_bin" -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install --upgrade pip
"$venv_dir/bin/python" -m pip install -r requirements.txt

mkdir -p data logs reports
for dir in *_applying_script; do
  mkdir -p "$dir/output"
done

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

echo "Environment ready."
echo "Run: source $venv_dir/bin/activate"
echo "Then: python job_portal_dashboard.py --port 8766"
