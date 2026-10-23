#!/usr/bin/env bash
# Run ON the V100; no Codex, workstation connection or host ML install required.
set -euo pipefail
train_script=$(realpath -- "${BASH_SOURCE[0]}")
cd "$(dirname "$train_script")/.."
exec python3 tools/learning/manage.py "$@"
