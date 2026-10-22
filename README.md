# yt2slp

An experimental foundation for reconstructing **approximate** playable Melee
replays from video. Video cannot recover every original input, RNG value or
hidden state. Observed, inferred and unknown values are separate types. Automatic gameplay recognition is not implemented. Local video ingestion,
manual-cue input search and rendered refinement are validated on two controlled
horizontal-motion cases. The native backend now exports genuine
selected-branch recordings, with bounded and complete timed-match Slippi playback validated
locally; this does not establish retail parity.

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

On Arch Linux, install the prerequisites with
`sudo pacman -S --needed git uv gcc`. The scripts accept either `gcc-14`/`g++-14`
or unversioned `gcc`/`g++` (GNU version 14+), and respect explicit `CC`/`CXX`
executable paths. Newer GCC versions are accepted but were not validated in the
original cloud build. Run the scripts with `&&` so a setup failure stops the
sequence: `bash scripts/setup.sh && bash scripts/build_game.sh`.

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

## Docker development environment (recommended for Arch)

Docker keeps the tested GCC 14 toolchain separate from the system compiler.
The image uses Debian 13, GCC/G++ 14 and Python 3.13; uv is pinned, and Python
dependencies remain locked by `uv.lock`. Debian security/package updates mean
this is a fixed toolchain family, not a byte-for-byte frozen OS snapshot.

Run from the repository on your Linux x86-64 host:

```bash
git pull --ff-only
bash scripts/docker.sh build
bash scripts/docker.sh setup
```

`build` installs tools into `yt2slp-dev:gcc14`. `setup` compiles the host and game
and runs both native suites plus Python tests. The first game compilation takes
several minutes; later runs reuse container build output. Docker must be running
and usable by your account. No privileged container, GPU, or display is needed.

The helper runs as your host UID/GID. Source edits are shared at `/work`, while
`.venv`, `build`, `.cache`, and `.local` use separate ignored host directories
under `.docker-state/`. Your existing Arch outputs remain untouched. Inspect
container logs on the host under `.docker-state/local/runs/`. Only the `docker/`
directory is sent as the image build context; no game assets enter the image.
Do not run host-built binaries inside the container or container-built Python
environments directly from the host. Use the helper for subsequent commands:

```bash
bash scripts/docker.sh run yt2slp doctor
bash scripts/docker.sh shell
# Inside the shell, the venv is already on PATH; working directory is /work.
```

For an asset-backed run, set the **host** ISO path before invoking the helper:

```bash
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run yt2slp doctor --require-game
bash scripts/docker.sh run yt2slp experiment \
  --script third_party/melee-unlocked/port/scripts/native_vs.txt \
  --retraces 3000 --seed 1 --time-base 0 --timeout 180 --repeat
```

The helper mounts that file read-only at `/assets/melee.iso` and sets the
container's `YT2SLP_ISO` accordingly. Slippi Dolphin is not needed for this
native experiment. The user has reported a successful 3000-retrace batch run (974 match
observations) with matching selected fields across two fresh Docker runs. The user subsequently validated the stepping path with their ISO; see below.

## Run a bounded experiment without Docker

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
restore a checkpoint and cannot prove complete game-state equality. The original cloud milestone had no ISO-backed game run; subsequent local
recording and playback validation is documented below. Batch recording is unsupported; live control sessions support explicit
selected-branch `record()` export. Process checkpoints are available in a
live control session, as described below. `initialize`
validates/binds paths, `run_script` initializes the game inside the native child,
and `observe` reads the last successful run's selected state. It never writes a
dummy `.slp`.

## Fixed matches and resumable stepping

The native backend now supports fixed stage/player settings and a live,
cooperative pause protocol. `start()` navigates to a match; `step()` advances
one **VI retrace**, preserving the game's stack and ordinary input/timing path.
The separate match-frame counter may advance differently. `observe()` does not
resume a paused session. Session-local process capture/restore is now available;
selected-branch recording is available.

Validate locally with your ISO after pulling and rebuilding the host:

```bash
git pull --ff-only
bash scripts/docker.sh setup
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run yt2slp step-experiment \
  --script third_party/melee-unlocked/port/scripts/native_vs.txt \
  --stage 31 --p1 2 --p2 20 --steps 600 \
  --seed 1 --time-base 0 --timeout 180 --repeat --check-input
```

This requests Fox vs. Falco on Battlefield. It checks pause stability, one-retrace
steps, matching repeated runs, and a different fighter trace from neutral input.
Logs and traces are retained under `.docker-state/local/runs/step-*`.
See [native stepping](docs/native-stepping.md) for the Python API, supported
configuration, timing semantics, protocol and test scope. Stock/time/item/team
rules retain fresh-game defaults. The user reported all stepping checks passing
with their ISO: 600 retraces advanced match frames 1 to 601. This was a local
validation, not a game run in the cloud workspace.

## Checkpoint capture and restore

The Linux backend retains one frozen process and resumes child branches from it,
preserving the stack, game memory and host state. Checkpoint handles are valid
only within the current session. Control sessions use an empty in-memory card;
batch runs retain disk-backed private cards. Recording follows process restores.

After pulling and running `bash scripts/docker.sh setup`, validate with:

```bash
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run yt2slp checkpoint-experiment \
  --script third_party/melee-unlocked/port/scripts/native_vs.txt \
  --stage 31 --p1 2 --p2 20 --warmup 240 --steps 180 \
  --seed 1 --time-base 0 --timeout 180
```

This compares identical and different-input continuations across three restores
of one checkpoint. See [process checkpoints](docs/process-checkpoints.md) for
API usage, lifecycle, retained traces and limitations. The user validated all three restores locally: capture at match frame 241 and
180-step continuations to 421, including divergence and return to original inputs.
Artifacts: `.docker-state/local/runs/step-2o7rj74b/`. Full-state equality and retail
parity are not established.

## Native recording and official playback

Live vanilla control sessions record game-generated events in memory. Call
`backend.record(Path("selected.slp"))` while paused to export the current branch;
restoring a checkpoint discards trial-branch events. Destinations must be new.
An unfinished match exports a partial replay with no invented Game End.

```bash
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/record_checkpoint_experiment.py
# Complete timed match, real Game End, and repeated restores across completed branches:
bash scripts/docker.sh run python scripts/record_complete_match.py
# Host playback configuration; do not use this path inside Docker:
export YT2SLP_DOLPHIN='/home/houndsolo/.config/Slippi Launcher/playback/Slippi_Playback-x86_64.AppImage'
```

The installed Playback Dolphin reports version 3.5.2 and is separate from Netplay
and the launcher. Real recording passed checkpoint-branch byte comparisons,
independent slippi-js parsing, and official playback through bounded and complete
timed-match recordings with resync disabled. The complete case has a genuine
timeout at frame 7200; its parser end method and placements are validated.
Dolphin result-state equality remains unmeasured. These are separate checks, not proof of
full-state equality or retail parity. See [recording and playback](docs/slippi-recording.md)
for exact evidence, parser installation, host/Docker path mapping and the verified
JSON playback interface.

Set `YT2SLP_DOLPHIN` to the official Playback executable on the host. The current doctor checks executable presence only;
neither parser acceptance nor executable presence establishes replay playback.

## Controlled reference benchmark

A first benchmark now records a known input sequence, captures official Playback
images and regenerated events, and compares nine native/official scalar fields
at exact frame keys. The 240..300 case passes across 122 player-frames and yields
a 61-frame lossless clip with rendered-timer labels. It uses local manually verified
glyph calibration; general video recognition and native/official image equality
remain unimplemented/unmeasured. See [reference benchmark](docs/reference-benchmark.md)
for capture, calibration, comparison commands and retained evidence.

```bash
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/record_benchmark.py
```

## Manual video cues and first input search

Local MP4 ingestion now preserves source PTS and decoded frames. A first bounded
checkpoint search uses manually reviewed action/facing/order/damage cues and an
explicit known start recipe. Five of 21 input schedules fit the controlled clip's
sparse cues; the chosen genuine replay passes parsing and official Playback.
A timer-aligned side-by-side review still shows position/camera differences.
This is a coarse input-search prototype with supplied initial conditions, not
automatic video reconstruction. No trained model is required. See
[manual reconstruction](docs/manual-reconstruction.md) for the schema, commands,
manual timer corrections, evidence and limits.

Rendered refinement now compares all five candidates using six manually chosen
fighter/stage image regions. It selects a closer continuation: whole-clip RGB
error falls from 24.22 to 5.29, and a separate post-selection check matches the
known source's nine state fields exactly. This first case uses supplied initial
conditions. See [rendered refinement](docs/rendered-refinement.md).

A second clip with delayed leftward movement passes the same search grid,
image objective and timer calibration: whole-clip RGB error falls from 31.13 to
5.28, with all nine source fields matching across 122 player-frames after
selection. Both cases still use supplied starting conditions and manual visual
annotations. See [controlled evaluation](docs/controlled-evaluation.md) for
the comparison, reproduction commands and remaining limits.

```bash
bash scripts/docker.sh run python scripts/ingest_video.py path/to/short.mp4 \
  --output .local/video-NEW
```

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
are committed on `yt2slp/linux-headless` and published to
[our fork](https://github.com/houndsolo/melee-unlocked/tree/yt2slp/linux-headless).
`.gitmodules` points to that fork so new clones can fetch the pinned commit.
A cloud snapshot is not a verified new-task restoration. Other reference repositories
are source research only, not runtime dependencies. Their pinned inspection
revisions are documented in `docs/engine-evaluation.md`.

The engine has GPL licensing and embeds components with their own notices;
retain its `LICENSE` and `NOTICE`. This repository does not redistribute game
images or claim ownership of the reference projects.
