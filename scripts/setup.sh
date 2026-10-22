#!/usr/bin/env bash
# Reproduce the asset-independent development environment without system writes.
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.cache/uv}"
command -v uv >/dev/null
command -v gcc-14 >/dev/null
command -v g++-14 >/dev/null
uv sync --locked
export PATH="$PWD/.venv/bin:$PATH"
git submodule update --init third_party/melee-unlocked
cmake -S third_party/melee-unlocked/port/linux/headless -B build/headless -G Ninja \
  -DCMAKE_MAKE_PROGRAM="$PWD/.venv/bin/ninja" -DCMAKE_BUILD_TYPE=Release
cmake --build build/headless -j "${YT2SLP_JOBS:-4}"
ctest --test-dir build/headless --output-on-failure
python -m pytest
yt2slp doctor
