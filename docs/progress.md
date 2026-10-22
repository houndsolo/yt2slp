# Progress

## First milestone — 2026-10-22

The Linux development foundation is implemented. Real simulation, integrated
checkpoint branching, recording and official playback remain unvalidated.
The user has not supplied an accessible game image; no asset was downloaded or
invented. The next experiment needs that prerequisite, not more package installs.

Completed:

- Preserved the initially empty checkout; used the existing configured Git
  identity, created an initial ignore-file commit, and made small local commits.
- Pinned Melee Unlocked, inspected all four requested projects and the actual
  upstream decompilation reference. See [evaluation](engine-evaluation.md).
- Created the dependency branch `yt2slp/linux-headless`. Scoped changes add an
  independent no-graphics/no-USB host target, fix SDK overlay selection in an
  existing test, and use POSIX UTC conversion outside Windows. No fast-math,
  global guard removal, or disabling of Slippi game code.
- Added Python package/CLI, doctor, typed evidence provenance and a backend
  contract with explicit unsupported operations. The batch adapter preserves
  logs and exact raw state fields, rejects partial/invalid output, and uses
  fresh processes and private card directories.
- Added locked tools, repeatable setup/game build scripts and exact README
  commands. Generated sources/assets/builds stay ignored.

## Validation record

| Layer | Result | What it establishes / does not establish |
| --- | --- | --- |
| Configuration | Passed | Linux x86-64, Python 3.12.14, GCC/G++ 14.2.0, CMake 3.31.6, Ninja 1.11.1; no graphics dependencies required for selected target |
| Host compilation | Passed | `build/headless/melee_headless` from existing native Linux services |
| Native game compilation | Passed | `build/game/melee_game.so`, all registered native test executables, retained `MU_NO_SLIPPI=OFF` |
| Image/ABI layout | Passed | Post-link image check reports `0x82800000..0x8340cef8`; generated 21 audio-exclusion ranges covering 122634 bytes. ELF load test resolves expected symbols below `0x84000000`. Not a game boot. |
| Headless/component tests | 9 passed | Version, fixed memory mapping, card/host services, input scripts, savestates, replay stream, state-region layout, practice model, animation. Final suite rerun through `scripts/setup.sh`. |
| Game-library tests | 23 passed | SDK/console layout, overlay/image/audio checks, command/match/content, credits, recording-start fixture, setjmp/alarm, preload, AX/synth/card, disc offsets, character-kind and real ELF loading |
| Python tests | 28 passed | Failure propagation, capabilities, provenance, digest decoding, private run paths, timeout and missing/short output. CSV transport fixtures are synthetic, not game output. |
| Game startup / fixed offline match | Unrun | No retail NTSC 1.02 ISO configured |
| Same-input/different-input checkpoint experiment | Unrun | No game startup; minimal host has no safe pause/restore integration |
| Snapshot component restore | Passed | Existing incremental snapshot tests, repeated `load_keep`, differential buffer checks. Not complete game/host-state equality. |
| Recording component rewind | Passed | Rejected events and character metadata removed; selected branch encodes identically to a clean selected stream. No game recorded. |
| `.slp` parsing | Unrun | No genuine simulation recording produced; slippi-js remains a research reference |
| Official Slippi Dolphin playback | Unrun | No configured official playback executable or recorded game |
| Windows build | Unrun | Windows branches retained; no Windows compiler/runtime tested |

Initial failures were diagnosed and fixed: uv's default home cache was read-only
(use a workspace cache); the AX fixture selected the wrong source tree; the
standalone stream needed `gmtime_r`; the newly added test initially used a short
Game End fixture rather than the declared six-byte payload. No test assertion
was disabled. Final results supersede those failed attempts.

Local logs (ignored): `build/game-build.log`, `build/game-tests.log`,
`build/setup-validation.log`, `build/game-setup-validation.log`, and CTest
`Testing/Temporary/LastTest.log` within each build directory. These are runtime
artifacts, not committed benchmarks or guarantees for another machine.

## Local commits and reproducibility

Main repository logical commits:

- `679ca57`: initial ignores.
- `63c92c1`: pin inspected upstream MU.
- `505cd56`: pin local tested headless engine changes.
- `1367198`: Python package, CLI, backend, tests, scripts and README.

Dependency commits on `yt2slp/linux-headless`:

- `6c3254c`: use the configured SDK overlay in the AX test.
- `f65be376bd486e74ec1d64a9601d40c2437994d2`: headless target, POSIX replay
  timestamp conversion and branch-rewind regression.

Following the user's push request, the dependency commits were published to
`houndsolo/melee-unlocked`, branch `yt2slp/linux-headless`, and `.gitmodules`
was updated to that fork. No history was rewritten. The parent commits are
being published to `houndsolo/yt2slp` on `main`. New-cloud-task restoration
has not been verified. See `git log` for subsequent documentation/fix commits.

Reusable cloud configuration was saved as a draft: `install_script` runs the
two tested setup/build scripts, and `start_skill` records activation, readiness
checks, the existing-checkout policy, unsupported capabilities and local-commit
limitations. No network or secret requirements were changed. Saving did not
publish the environment; review/save in environment settings and publication
remain user actions. No new-task restoration is claimed.

## Subsequent environment work

Docker environment: added `docker/Dockerfile` and `scripts/docker.sh` for
Debian 13 / GCC 14.2.0 / Python 3.13.5, with uv 0.12.23. A fresh isolated
container build passed all 9 host, 36 Python and 23 game-library tests,
including `native_disc_layout`. Container outputs and the venv live under
ignored `.docker-state/`, separate from the Arch builds. Verified host UID/GID
ownership and a read-only ISO bind mount using an empty non-game fixture.
No real game boot was performed. The user's GCC 16 exit-4 collision-box failure
also persists with SLP vectorization disabled; its underlying cause remains
unresolved. The container supplies a validated alternative toolchain, not proof
that the GCC 16 issue has been fixed.

Arch setup follow-up: setup previously exited silently when `uv` or Debian's
`gcc-14`/`g++-14` names were missing. Running the game build afterward inside an
uninitialized engine directory made Git discover the parent repository and
report a nested-submodule pathspec error. Both scripts now report missing
prerequisites, accept GNU 14+ compilers under versioned or unversioned names,
and respect `CC`/`CXX`. The game build initializes the outer submodule first.
Validation after this fix: 36 Python tests, 9 headless tests and 23 game-library
tests passed through the scripts on the cloud GCC 14 machine. Unversioned
compiler discovery was also exercised; an actual Arch/GCC 15+ build is not yet
verified. Use `bash scripts/setup.sh && bash scripts/build_game.sh`.

## Fixed matches and resumable stepping — 2026-10-22

Native dependency commit: `c697e5b` on `yt2slp/linux-headless`.

The user reported that the Docker batch experiment completed 3000 retraces,
including 974 match observations, twice with matching selected fields. This
supersedes the initial local-startup uncertainty; it is user-reported evidence,
not a game run in the cloud workspace.

Implemented the existing match override in the minimal Linux CLI and added
validated Python settings for two players, characters/costumes/CPU settings,
and Battlefield/Final Destination. Other rules retain fresh-game defaults.
A private socket protocol blocks inside the existing retrace observer, retains
the live game stack, and advances one VI retrace per step. Ordinary PAD polling,
game timing constants, game source, math flags and ABI are unchanged. Observations
preserve raw bits and keep retrace/match-frame counters separate.

Added pause/step/observe lifecycle, bounded boot, timeouts, process cleanup,
retained logs/config/input/state traces, and a three-run local validation command.
Checkpoint capture/restore and recording remain explicit unsupported operations.
No checkpoint or replay is fabricated. Native protocol tests use synthetic
states, and Python integration tests drive the same compiled control implementation.
See [native stepping](native-stepping.md) for exact semantics and the local ISO
command. Validation: `bash scripts/docker.sh setup` rebuilt the modified host and passed
10 host/component tests, 76 Python tests and 23 game-library tests in the GCC 14
container. The host Python suite also passed all 76 tests. The new command was
exercised end to end against the compiled synthetic protocol fixture, including
same-input and neutral-input comparisons. No ISO-backed stepping or official
playback validation was performed here. Existing reusable environment setup
commands remain sufficient; no environment draft changes were needed.

Next: run that command locally with the ISO, then investigate any observed
input/timing differences before building checkpoint/recording integration.
