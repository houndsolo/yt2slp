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

These commits are local only. No push or history rewriting was performed.
The dependency commits **must be published to a fork**, and `.gitmodules`
updated to that fork, before a new remote clone can fetch the parent's gitlink.
The current workspace is usable; fresh-clone and new-cloud-task restoration
have not been verified. See `git log` for subsequent documentation/fix commits.

## Next concrete task

Once an ISO path is available, execute the README's bounded script with fixed
seed/timebase, inspect that it actually enters a match, and expose the already
implemented match override through the headless CLI to fix the setup. Then add
the cooperative in-match pause/restore protocol and coordinate memory, host
state and replay-stream marks. Until that exists, `step`, `capture`, `restore`
and `record` return actionable unsupported-operation errors. No model training,
video recognition or graphics port is part of this milestone.
