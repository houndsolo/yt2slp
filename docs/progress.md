# Project roadmap and progress

Updated 2026-10-22. The goal is to turn Melee video into an **approximate playable
Slippi replay**, with evidence showing how closely it matches the video. Video
cannot uniquely recover original inputs, RNG or hidden state; reconstructed
values must remain distinguishable from observations and unknowns.

**Current position:** the native simulation foundation works, including stepping,
checkpoint branching and genuine replay export. Bounded and complete timed-match recordings have
passed independent parsing and actual official Playback Dolphin progression.
Video ingestion, visual state estimation and input reconstruction are not yet
implemented. There is no end-to-end video-to-replay command yet.

Checked items below are implemented and validated within their stated scope.
Unchecked items are remaining work. Proposed later work is a roadmap, not a
promise that its design or acceptance thresholds have already been settled.

## Milestone overview

| Milestone | Status | Completion boundary |
| --- | --- | --- |
| 1. Reproducible native development environment | Complete for Linux/GCC 14 | Build and test the host/game without committing game assets |
| 2. Controllable simulation and checkpoint branching | Complete for the initial supported scope | Boot a fixed match, apply inputs, pause, observe, capture and repeatedly restore |
| 3. Genuine recording and official playback | Bounded and complete timed matches validated; broader cases remain | Export only the selected branch, parse it independently, and play it in official Dolphin |
| 4. Reference comparison and controlled benchmarks | Not implemented | Measure agreement between native simulation, official playback and rendered observations |
| 5. Video ingestion and observation extraction | Not implemented | Produce a timestamped, uncertainty-aware observation timeline from a supported clip |
| 6. Input and hidden-state reconstruction | Not implemented | Search simulation branches for a playable sequence that matches observations |
| 7. End-to-end reconstruction and review | Not implemented | Video in; selected `.slp`, comparison evidence and limitations out |
| 8. Broader evaluation and practical usability | Development tooling exists; reconstruction evaluation remains | Reproduce results on held-out clips and document supported cases and failure modes |

## 1. Reproducible native development environment

- [x] Audit engine alternatives and select Melee Unlocked's existing native Linux
  source game, isolated in a child process. Pin the engine and nested game source.
- [x] Build an independent headless host without display, GPU or USB dependencies.
- [x] Build the real native game library with Slippi game code enabled. Preserve
  game math flags, ABI, console timing and low-address memory requirements.
- [x] Provide locked Python tools, setup/build scripts, diagnostics and tests.
- [x] Provide a Debian 13 / GCC 14 Docker environment and separate its build/cache
  output from Arch host output. Use Docker for native builds and tests.
- [x] Keep ISOs, extracted/generated game material, generated recordings and experiment
  artifacts ignored. Mount the user's ISO read-only.
- [x] Publish dependency changes before updating the parent submodule gitlink.

GCC 16 previously failed a native layout test. GCC 14 is the validated route;
the GCC 16 problem has not been fixed. Windows and restoration into a fresh cloud
task have not been validated. See [README setup](../README.md) and
[engine evaluation](engine-evaluation.md).

## 2. Controllable simulation and checkpoint branching

- [x] Boot the user's retail NTSC 1.02 ISO and run bounded scripted experiments.
- [x] Configure two players, characters, costumes, human/CPU settings and
  Battlefield/Final Destination. Other rules retain fresh-game defaults.
- [x] Retain a live game stack while paused; advance one **VI retrace** per step.
  Keep the separate match-frame counter explicit and preserve ordinary PAD polling.
- [x] Observe selected state fields without resuming; retain raw float bits.
- [x] Validate pause stability, repeat-run agreement and observable input effects.
- [x] Capture one reusable, session-local Linux process checkpoint and restore
  game/host private memory, native stack, input state, clocks and callbacks.
- [x] Keep control-session memory cards in memory so discarded branches cannot
  change future saves. Retain private disk-backed cards for batch runs.
- [x] Validate identical continuations, divergent inputs, and return to the
  original continuation after the divergent branch across three restores.
- [x] Handle invalid/stale checkpoint handles, timeouts, process failures and cleanup.

Local evidence: 600 steps advanced match frames 1..601. The checkpoint experiment
captured at frame 241 and ran four 180-step continuations to 421. The user reported
all three restores passing, and the retained traces agree. Artifacts:
`.docker-state/local/runs/step-2o7rj74b/`.

These comparisons cover selected observations, not a complete memory hash or
retail parity. Portable checkpoint files and multiple retained checkpoints are
not implemented; add them only if the reconstruction strategy requires them.
See [stepping semantics](native-stepping.md) and
[checkpoint lifecycle](process-checkpoints.md).

## 3. Genuine recording and official playback

- [x] Inspect the game's replay-event hooks and existing native stream encoder.
- [x] Record genuine game-generated events in private process memory from match
  start. Export the selected branch and its pre-checkpoint prefix while paused.
- [x] Discard trial-branch recording events and metadata when restoring process
  memory. Validate matching encoded bytes after identical/restored continuations
  and different bytes for different-input continuations.
- [x] Publish exports exclusively and atomically; reject unsupported operations
  and malformed transport. Never synthesize Game End, winners or replay events.
- [x] Locate official Playback Dolphin separately from Netplay and the launcher;
  verify installed version 3.5.2, actual CLI and JSON replay-request interface.
- [x] Configure/document `YT2SLP_DOLPHIN` and host versus Docker paths. Run official
  playback on the Arch host with an isolated profile and virtual display.
- [x] Validate a bounded generated `.slp` independently with pinned
  `@slippi/slippi-js@9.1.3`, including settings and contiguous player events.
- [x] Validate actual official playback through the bounded replay's recorded
  interval with resync disabled. Keep parser acceptance and playback evidence separate.
- [x] Validate a complete timed match's genuine Game End, final frame, end method
  and placements in the recording and independent parser, and validate official
  playback through that final frame. Dolphin result-state equality remains unmeasured.
- [x] Restore from completed branches to a pre-ending checkpoint; verify that
  ended status clears, identical endings encode identically and post-ending
  callbacks are safe without changing replay bytes.
- [ ] Exercise longer recordings and more supported match/input cases before
  treating one successful bounded example as general playback compatibility.

The selected bounded replay is 181,236 bytes, with 545 contiguous frames
-123..421. Original, identical and selected continuations encode identically;
the divergent branch differs. Official Playback reports contiguous frames
-123..422. The replay has **no Game End** because it was exported mid-match;
closing the harness does not complete it. Batch recording, non-vanilla/modded
recording and recording across multiple matches remain unsupported.

The complete timed-match follow-up runs to a genuine timeout at frame 7200:
7,324 contiguous frames -123..7200, end method 1, no quit initiator, and placements
[1, 0, -1, -1]. Capture at 6901 supports three restores across four completed
continuations; original/identical/selected files match at 2,952,212 bytes, while
the divergent file differs. Extra post-ending steps leave each replay unchanged.
Official Playback reports the same file path and final frame, with contiguous
-123..7200 progression and resync disabled. Its report is bound to the independent
parser report by replay SHA-256. The request does not force an `endFrame` cutoff.

Implemented `recording_status()` without advancing simulation and installed the
previously missing `replay_finished` host callback, which the real game calls
at completion/scene exit. No game source, physics, ABI or timing constants changed.

See [recording and playback](slippi-recording.md) for commands, configuration,
transport details and artifact locations. Next: reference comparison/frame capture
in milestone 4; expand ending/match coverage before claiming general compatibility.

## 4. Reference comparison and controlled benchmarks

This is the next foundation for evaluating reconstruction quality. Playback frame
progression establishes that a file plays; it does not establish that native and
Dolphin states or rendered images agree.

- [ ] Define an initial supported reconstruction case: short continuous footage,
  known stage/characters, explicit start conditions and a limited input space.
  Set measurable acceptance thresholds before claiming a successful reconstruction.
- [ ] Automate official Playback frame capture and align replay frames with
  native observations. Account for preroll, pauses and VI versus match-frame timing.
- [ ] Compare native selected states with independent replay/playback evidence;
  compare rendered observations where available. Identify and document divergence
  rather than changing physics or enabling resync to conceal it.
- [ ] Create controlled reference clips from known inputs and retain their input
  sequences, replay events, observations, frame mapping and tool/build identities.
- [ ] Establish repeatable comparison metrics for positions, actions, stocks,
  damage, event timing and visual agreement, including tolerances and exclusions.

Acceptance: a reproducible benchmark can report where agreement holds, where it
fails, and what remains unmeasured. Full retail parity is not assumed or a reason
to postpone measuring a narrower supported case.

## 5. Video ingestion and observation extraction

- [ ] Decode a local clip while preserving timestamps and recording its frame
  rate, resolution, duplicate/dropped frames, cuts and unsupported segments.
- [ ] Identify the gameplay region, stage, characters and player identities;
  separate overlays, HUD, camera motion and screen coordinates from world position.
- [ ] Align the clip timeline to candidate game frames, accounting for capture
  rate, pauses, speed changes and gaps instead of assuming one video frame per step.
- [ ] Extract and track visible evidence: stocks, damage, fighter locations,
  actions and useful events. Represent occlusion and ambiguous observations explicitly.
- [ ] Extend the existing `Evidence` provenance types into a timeline schema with
  source frame/time references, uncertainty and candidate values where needed.
- [ ] Support manual observations/corrections so a short reconstruction can be
  tested before automatic recognition is reliable.
- [ ] Measure observation accuracy against annotated controlled clips, including
  cases where the system should leave a value unknown.

Acceptance: a supported clip produces a reviewable observation timeline. The
existing observed/inferred/unknown types are completed groundwork, not an
implemented video recognition system.

## 6. Input and hidden-state reconstruction

- [ ] Establish candidate initial states/settings and unknowns, including RNG,
  rather than silently substituting convenient defaults for missing evidence.
- [ ] Define an objective that compares simulated outcomes with observations
  using their uncertainty, timing and provenance.
- [ ] Implement bounded candidate-input search over short windows using the
  existing step/capture/restore operations. Retain alternatives when evidence
  cannot distinguish them; do not claim to recover unique original inputs.
- [ ] Join windows into a consistent trajectory and handle drift, failed searches
  and conflicting observations. Add more checkpoint capacity only if needed.
- [ ] Persist search inputs, configuration, costs and progress so reconstruction
  can be inspected, reproduced and resumed with clearly defined session limits.
- [ ] Export only the selected continuation and test that rejected candidates
  never leak into its events or metadata.
- [ ] Recover an acceptable playable trajectory for a controlled short clip,
  initially using manual observations, then the video observation pipeline.

Acceptance: a known reference clip can be reconstructed within the predefined
error bounds, with uncertainty and failures reported. Exact original inputs and
hidden state are not required or claimed.

## 7. End-to-end reconstruction and review

- [ ] Provide a command/workflow connecting video ingestion, observations,
  reconstruction, selected-branch export and validation.
- [ ] Parse every exported replay and run official playback; report each result
  independently and retain evidence for failed as well as successful runs.
- [ ] Produce aligned source/reconstruction comparisons and a report of match
  quality, inferred settings, unknowns and unsupported portions of the clip.
- [ ] Allow corrections and reruns without replacing the original observations
  or claiming that an incomplete reconstruction covers the whole video.
- [ ] Distinguish clip-only partial recordings from complete games with real
  Game End events. Preserve that distinction in outputs and user documentation.

Acceptance: one supported short video can be processed into a playable `.slp`
and an honest comparison report using a documented reproducible workflow.

## 8. Broader evaluation and practical usability

- [x] Supply development diagnostics, bounded experiment commands, retained logs
  and native/Python component tests.
- [ ] Evaluate end-to-end reconstruction on held-out clips, including camera
  changes, occlusion, compression artifacts and timing irregularities.
- [ ] Publish supported cases, accuracy/error distributions, failure rates,
  runtime/resource costs and reproducibility instructions. Keep private game
  material and generated artifacts out of Git.
- [ ] Improve search performance and support more stages, characters, rules or
  video conditions only after measuring the initial case.
- [ ] Add regression coverage for established reconstruction behavior and verify
  the documented setup from a fresh checkout/environment.

Windows, online play, mods, a graphical application, portable checkpoints and
arbitrary full-match video support are possible extensions, not implemented
features or prerequisites for the first short-clip reconstruction.

## Latest validation and retained evidence

The last implementation validation used Docker GCC 14 and passed **122 Python,
10 host/component, 23 game-library and 9 independent parser tests**. Synthetic protocol/component tests
establish their tested behavior; the following local ISO runs provide separate
gameplay, recording and playback evidence.

| Evidence | Result / retained location |
| --- | --- |
| Batch and stepping | User-reported matching 3000-retrace runs; 600-step check advanced match frames 1..601 with stable pauses and input effects |
| Checkpoint experiment | Capture 241, four continuations to 421, three successful restores; `.docker-state/local/runs/step-2o7rj74b/` |
| Recording and independent parser | Branch-byte comparisons and parser report; `.docker-state/local/runs/step-qa9h0_nl/` |
| Reusable recording experiment | Same selected replay bytes and matching selected states; `.docker-state/local/runs/step-jrevwdnh/recording-result.json` |
| Bounded official Playback 3.5.2 | Contiguous -123..422 frame reports, resync disabled; `.local/playback-full/result.json` and `stdout.log` |
| Complete timed match and restoration | Capture 6901, three restores, genuine timeout at 7200; `.docker-state/local/runs/step-cwrg_5u4/complete-result.json` |
| Complete-match independent parser | Final frame 7200, timeout method 1, placements [1, 0, -1, -1]; `parser-result.json` and `divergent-parser-result.json` in that run |
| Complete official Playback 3.5.2 | Exact replay path/final-frame checks, contiguous -123..7200 progression, resync disabled; `.local/playback-complete/result.json` and `stdout.log` |

The selected replay in both recording runs has SHA-256
`46b196b913b9a81bc501ddfcdd6f28c2710aabf665b0597d9059c9511e7e5dd2`.
Artifacts are ignored local evidence, not files guaranteed to exist in another
checkout. The complete selected recording has SHA-256
`5605bab19d66b2fdaaf0148ba924c5867fd9b17e3dd7b52f94c217856af1144b`.
Full-state equality, rendered-image agreement, Dolphin/native result-state
agreement, stock/LRAS endings and retail parity remain unestablished.

## Completed implementation milestones

| Parent commit | Engine commit | Delivered |
| --- | --- | --- |
| `1367198` and subsequent setup fixes | `f65be37` | Initial native host, Python backend, component checks and setup documentation |
| `2d30a15` | Existing engine pin | Validated GCC 14 Docker environment |
| `ad88399` | `c697e5b` | Fixed matches and resumable VI stepping |
| `97005ca` | `862191c` | One reusable process checkpoint and branch validation |
| `657c3db` | `b87fb67` | Genuine selected-branch recording, independent parsing and bounded official playback |

The complete timed-match follow-up pins engine `18ded4f`, published before its
parent gitlink update. It adds the missing completion callback and recording
status; the parent adds the complete-match experiment and stricter independent
parser/official frame-report checks.

Changes are published to `houndsolo/yt2slp` on `main` and
`houndsolo/melee-unlocked` on `yt2slp/linux-headless`. See Git history for the
smaller setup and documentation commits. Earlier milestone test counts and
"unrun" results have been superseded by the current validation record above.
