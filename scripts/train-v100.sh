#!/usr/bin/env bash
# Run ON the V100; no Codex, workstation connection or host ML install required.
set -euo pipefail
train_script=$(realpath -- "${BASH_SOURCE[0]}")
cd "$(dirname "$train_script")/.."
if [[ -f configs/vision-v100-sequence.json ]]; then
  exec python3 tools/learning/manage.py --config configs/vision-v100-sequence.json "$@"
fi
if [[ -f configs/vision-v100-corpus.json ]]; then
  exec python3 tools/learning/manage.py --config configs/vision-v100-corpus.json "$@"
fi
exec python3 tools/learning/manage.py "$@"
