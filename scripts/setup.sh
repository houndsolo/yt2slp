#!/usr/bin/env bash
# Reproduce the asset-independent development environment without system writes.
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.cache/uv}"
for tool in git uv; do
  if ! command -v "$tool" >/dev/null; then
    echo "yt2slp: missing $tool. On Arch: sudo pacman -S --needed git uv gcc" >&2
    exit 1
  fi
done
uv sync --locked
export PATH="$PWD/.venv/bin:$PATH"
compiler_paths=$(python -m yt2slp.toolchain)
mapfile -t compilers <<< "$compiler_paths"
export CC="${compilers[0]}" CXX="${compilers[1]}"
git submodule update --init third_party/melee-unlocked
cmake -S third_party/melee-unlocked/port/linux/headless -B build/headless -G Ninja \
  -DCMAKE_MAKE_PROGRAM="$PWD/.venv/bin/ninja" -DCMAKE_CXX_COMPILER="$CXX" -DCMAKE_BUILD_TYPE=Release
cmake --build build/headless -j "${YT2SLP_JOBS:-4}"
ctest --test-dir build/headless --output-on-failure
python -m pytest
yt2slp doctor
