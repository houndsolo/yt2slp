#!/usr/bin/env bash
# Full native game build; no ISO needed to compile. Never patch the nested checkout.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ] || [ ! -x .venv/bin/cmake ] || [ ! -x .venv/bin/ninja ]; then
  echo "yt2slp: development tools are missing; run bash scripts/setup.sh successfully first." >&2
  exit 1
fi
export PATH="$PWD/.venv/bin:$PATH"
compiler_paths=$(python -m yt2slp.toolchain)
mapfile -t compilers <<< "$compiler_paths"
export CC="${compilers[0]}" CXX="${compilers[1]}"
engine="$PWD/third_party/melee-unlocked"
# git -C inside an empty submodule directory otherwise discovers the parent
# repository and reports a misleading nested-submodule pathspec error.
git submodule update --init third_party/melee-unlocked
git -C "$engine" submodule update --init sourceport/extern/melee
mkdir -p build
if [ ! -d build/decomp ]; then
  git clone --shared "$engine/sourceport/extern/melee" build/decomp
  git -C build/decomp checkout --detach 039c4bf4ca33338c35d21901ad19b7ede19d19ad
fi
python "$engine/tools/prepare_native_sources.py" --decomp "$PWD/build/decomp"
cmake -S "$engine/sourceport/game" -B build/game -G Ninja \
  -DCMAKE_MAKE_PROGRAM="$PWD/.venv/bin/ninja" \
  -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" \
  -DMELEE_DECOMP_DIR="$PWD/build/decomp" -DMELEE_CPU_BASELINE=AVX2 \
  -DMU_NO_SLIPPI=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build/game --target mu_game_tests -j "${YT2SLP_JOBS:-4}"
ctest --test-dir build/game --output-on-failure
