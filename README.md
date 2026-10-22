# yt2slp

An experimental foundation for reconstructing **approximate** playable Melee
replays from video. Video cannot recover every original input, RNG value or
hidden state. Observed, inferred and unknown values are separate types. This
milestone does not implement video recognition or claim to generate playable
replays yet.

The selected engine is the existing native Linux Melee Unlocked source host,
isolated in a child process. See [engine evaluation](docs/engine-evaluation.md)
for the source audit and [progress](docs/progress.md) for measured results and
remaining blockers.

## Setup on Linux x86-64

Prerequisites: Python 3.11+, `uv`, Git, GCC/G++ 14+, and an AVX2/FMA-capable CPU
for the default native game build. CMake and Ninja are installed from `uv.lock`.
On Debian 13, the compiler packages are `gcc-14` and `g++-14`. No display server,
GPU, USB adapter, Docker, ISO, or Slippi credentials are needed for the portable
host tests. Use the existing checkout in cloud tasks; do not create a worktree
unless explicitly requested.

```bash
cd /workspace/yt2slp  # or your checkout
bash scripts/setup.sh
source .venv/bin/activate
yt2slp doctor
yt2slp capabilities
```

`setup.sh` installs locked Python tools, builds the separate headless target,
runs CTest and Python tests, then checks readiness. It uses four build jobs;
set `YT2SLP_JOBS` to change that. Downloads use the existing proxy and TLS trust.
No service needs to stay running. Build output and logs are disposable and
ignored. The upstream snapshot stress test may take around a minute or longer.

To build the actual native game library and its existing tests (no ISO needed
for compilation):

```bash
bash scripts/build_game.sh
```

This initializes only the pinned `doldecomp/melee` dependency, copies it to an
ignored `build/decomp` checkout, and applies MU's released native patch there.
The nested source submodule stays clean. Linux's LP64 adaptation is generated
in `build/game/console-lp64`. The script keeps `MU_NO_SLIPPI=OFF`, the upstream
AVX2/FMA baseline, and the upstream game math flags. `build/decomp` uses a local
Git alternate to the nested checkout; recreate it using the script if that
object store is removed. Aurora is not needed for these targets.

## Run a bounded experiment when assets are available

Provide your own legally obtained, uncompressed Melee NTSC 1.02 ISO. No game
image, extracted asset or generated game source is committed. The native loader
checks the disc header and retail DOL SHA-1; a doctor header check is not that
full validation. Environment values below are paths, not credentials.

```bash
export YT2SLP_ISO=/absolute/path/to/Melee-NTSC-1.02.iso
yt2slp doctor --require-game
yt2slp experiment \
  --script third_party/melee-unlocked/port/scripts/native_vs.txt \
  --retraces 3000 --seed 1 --time-base 0 --timeout 180 --repeat
```

The upstream script drives menus and then movement/jump/attack inputs. Its
timings are a starting point, **not a verified match recipe in this environment**.
The CLI rejects menu-only output. Every run uses a fresh process and private
memory-card directory in `.local/runs/run-*`, retaining `host.log` and
`state.csv`, including failed runs. `--fast` removes wall-clock pacing, not
simulation ticks. `--vanilla-game` requests the engine's vanilla options; it
does not establish parity with retail Melee.

`--repeat` compares selected state fields across two fresh boots. It does not
restore a checkpoint and cannot prove complete game-state equality. No match
has been run without an ISO. The current backend deliberately raises
`UnsupportedOperation` for `step`, `capture`, `restore` and `record`. `initialize`
validates/binds paths, `run_script` initializes the game inside the native child,
and `observe` reads the last successful run's selected state. It never writes a
dummy `.slp`.

For later playback validation, set `YT2SLP_DOLPHIN` to your official Slippi
Playback executable. The current doctor checks executable presence only;
neither parser acceptance nor executable presence establishes replay playback.

## Development checks

```bash
source .venv/bin/activate
python -m pytest
ctest --test-dir build/headless --output-on-failure
ctest --test-dir build/game --output-on-failure # after build_game.sh
git status --short
git -C third_party/melee-unlocked status --short
```

Python transport tests use explicit synthetic CSV fixtures; they are not game
simulations. Native tests exercise real engine components, including incremental
snapshot restore, script timing, card I/O, low memory mapping and replay-stream
rewind. Their scope is described in the evaluation.

## Dependency commits and reproducibility

Melee Unlocked is pinned by the Git submodule gitlink; the inspected upstream
base is `6177fd31acf250fe733089cd4471ce9c87969cf3`. Our small dependency changes
are committed on its local `yt2slp/linux-headless` branch. **Those commits are not
published. A fresh remote clone cannot fetch our updated gitlink until a fork
containing those commits is published and `.gitmodules` points to it.** Nothing
was pushed. The current checkout and local commits remain usable; a cloud
snapshot is not a verified fresh-clone restoration. Other reference repositories
are source research only, not runtime dependencies. Their pinned inspection
revisions are documented in `docs/engine-evaluation.md`.

The engine has GPL licensing and embeds components with their own notices;
retain its `LICENSE` and `NOTICE`. This repository does not redistribute game
images or claim ownership of the reference projects.
