#!/usr/bin/env bash
# Full native game build; no ISO needed to compile. Never patch the nested checkout.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.venv/bin:$PATH"
engine="$PWD/third_party/melee-unlocked"
git -C "$engine" submodule update --init sourceport/extern/melee
mkdir -p build
if [ ! -d build/decomp ]; then
  git clone --shared "$engine/sourceport/extern/melee" build/decomp
  git -C build/decomp checkout --detach 039c4bf4ca33338c35d21901ad19b7ede19d19ad
fi
python "$engine/tools/prepare_native_sources.py" --decomp "$PWD/build/decomp"
cmake -S "$engine/sourceport/game" -B build/game -G Ninja \
  -DCMAKE_MAKE_PROGRAM="$PWD/.venv/bin/ninja" \
  -DCMAKE_C_COMPILER=gcc-14 -DCMAKE_CXX_COMPILER=g++-14 \
  -DMELEE_DECOMP_DIR="$PWD/build/decomp" -DMELEE_CPU_BASELINE=AVX2 \
  -DMU_NO_SLIPPI=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build/game --target mu_game_tests -j "${YT2SLP_JOBS:-4}"
ctest --test-dir build/game --output-on-failure
