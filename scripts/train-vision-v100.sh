#!/usr/bin/env bash
# Matched visual-state experiment; controller training remains in train-melee.
set -euo pipefail
state_script=$(realpath -- "${BASH_SOURCE[0]}")
cd "$(dirname "$state_script")/.."
exec python3 tools/learning/manage.py --config configs/vision-v100-state.json "$@"
