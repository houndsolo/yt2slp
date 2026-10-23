# Project roadmap and progress

Updated 2026-10-22. The goal is to turn Melee video into an **approximate playable
Slippi replay**, with evidence showing how closely it matches the video. Video
cannot uniquely recover original inputs, RNG or hidden state; reconstructed
values must remain distinguishable from observations and unknowns.

**Current position:** the native simulation foundation works, including stepping,
checkpoint branching and genuine replay export. Bounded and complete timed-match recordings have
passed independent parsing and actual official Playback Dolphin progression.
A controlled nine-field comparison, timer-labelled reference capture, local video
decoding and bounded input search now work for five controlled clips: right, delayed left,
movement/release/reversal, a jump, and a two-window short/full-hop sequence.
The first two use a single-change grid;
the later cases use timed axis/button phases. Manual fighter/stage regions select a closer
continuation using the same image objective and timer calibration. Separate
post-selection checks match each known source's nine state fields exactly.
The jump retains four tied input programs with distinct recorded controls and
identical official images. All cases use supplied starting conditions and manual
annotations. A single host command now runs consecutive annotated windows,
verifies selected history between sessions and validates the joined replay.
Automatic gameplay recognition, unknown-start recovery and general
video-to-replay reconstruction remain unimplemented.

Checked items below are implemented and validated within their stated scope.
Unchecked items are remaining work. Proposed later work is a roadmap, not a
promise that its design or acceptance thresholds have already been settled.

## Milestone overview

| Milestone | Status | Completion boundary |
| --- | --- | --- |
| 1. Reproducible native development environment | Complete for Linux/GCC 14 | Build and test the host/game without committing game assets |
| 2. Controllable simulation and checkpoint branching | Complete for the initial supported scope | Boot a fixed match, apply inputs, pause, observe, capture and repeatedly restore |
| 3. Genuine recording and official playback | Bounded and complete timed matches validated; broader cases remain | Export only the selected branch, parse it independently, and play it in official Dolphin |
| 4. Reference comparison and controlled benchmarks | Five cases, including a 161-frame sequence, validated; broader cases remain | Measure agreement between native simulation, official playback and rendered observations |
| 5. Video ingestion and observation extraction | Local decoding/manual cues validated; automatic recognition remains | Produce a timestamped, uncertainty-aware observation timeline from a supported clip |
| 6. Input and hidden-state reconstruction | Single-window phases and consecutive windows with verified history validated; unknown starts/backtracking remain | Search simulation branches for a playable sequence that matches observations |
| 7. End-to-end reconstruction and review | One host workflow for annotated, supplied-start windows; general observations/visual acceptance remain | Video in; selected `.slp`, comparison evidence and limitations out |
| 8. Broader evaluation and practical usability | Five controlled sources evaluated; real tournament footage is next | Reproduce results on held-out clips and document supported cases and failure modes |

## Immediate priorities after inspecting the real video

The supplied tournament clip changes the order of work. More generated fixtures
and model training are not the immediate bottleneck: the first real opening needs
correct control timing, two active input programs and an explicit image mapping.
The earlier milestones remain useful foundations, not a claim that this video
has already been reconstructed.

| Order | Work | Current status / completion boundary |
| --- | --- | --- |
| 1 | Reproduce a supported start and control the pre-clock opening | Stage/ports/stock rules validated; optional early control and genuine branch recording validated. Requested playable frames -39..140 are nine-field exact in official Playback. Full Ready audit retains one float-word mismatch at -113. |
| 2 | Carry the real recipe and two players through search | Next: explicit ports/rules and simultaneous input phases, signed replay-frame keys through Ready, checkpoint branching and fresh selected-history reproduction. Current search still assumes Fox/Falco/Battlefield and one active controller. |
| 3 | Prepare source-only opening observations and comparison geometry | Intake/crop/timer readings exist. Freeze manual action/damage/order evidence and uncertainty before search; define/validate the source-to-render transform. Do not treat the first clock decrement as the first playable frame. |
| 4 | Reconstruct one short opening from the supplied footage | Search a bounded declared grid with unknown RNG/codes left explicit; retain alternatives and failed candidates. No original replay or hidden-state oracle is available for selection. |
| 5 | Validate and review the actual reconstructed result | Genuine selected `.slp`, independent parser, official playback, and an aligned source/comparison clip with measured errors. Engine/native agreement and source-video similarity are separate gates. |
| 6 | Expand coverage, then automate observations | Try another real segment/clip, handle drift/backtracking and measure manual-annotation bottlenecks. Build/train vision components only for measured recognition gaps. |

The current seed/time-base choices are simulation hypotheses, not recovered
source values. General starting-state/RNG recovery, camera/world-coordinate
measurement, broad visual acceptance and arbitrary full-match reconstruction
remain open. See [tournament intake](tournament-video-intake.md),
[setup validation](tournament-start.md) and [pre-clock control](preroll-control.md).

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
  Battlefield/Final Destination; extend to Yoshi's Story, two explicit physical
  ports and stock/countdown rules, with a separate ISO/parser/official probe.
  Unspecified rules retain fresh-game defaults.
- [x] Add optional early control and checkpoints while the native match counter is
  zero; observe signed recording frames separately. Real negative-frame branch
  recording/fresh reproduction and official playable-interval checks pass.
- [ ] Resolve the separate one-word Ready-state discrepancy at replay frame -113
  before claiming complete pre-clock native/official equality; no tolerance added.
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

Reference comparison provides a foundation for evaluating reconstruction quality. Playback frame
progression establishes that a file plays; it does not establish that native and
Dolphin states or rendered images agree.

- [x] Define a first controlled reference case: unpaused vanilla Fox/Falco on
  Battlefield, fixed requested boot inputs, a neutral/right input sequence, and
  game frames 240..300. Require exact selected scalar words and complete coverage.
- [x] Capture actual official Playback images and regenerated game events with
  resync disabled; retain private profiles, requests, inputs and tool/build identities.
- [x] Compare nine post-frame fields at exact frame/player keys and independently
  check the seven common native observation fields without fitting a time shift.
- [x] Label a controlled reference clip from its rendered countdown HUD using
  local manually verified glyph calibration. Require every requested label exactly
  once; preserve unknowns and reject ambiguous, missing or reordered labels.
- [x] Retain a 61-frame lossless clip, frame/timer/image mapping, exact mismatch
  counts, maximum absolute errors, RMSE and first-difference diagnostics.
- [x] Validate a second source with delayed leftward movement, preserving the
  original source generator's replay bytes. Both sources pass the same nine-field,
  native-observation and timer-coverage checks over 240..300.
- [x] Validate a third source with movement, release and reversal against the same
  state/observation/timer criteria, without changing game timing or math.
- [x] Validate a fourth source with a jump against those same criteria; independently
  parse actual recorded X/Y masks and press/release durations in candidate replays.
- [x] Measure Fox's short/full-hop boundary at one/two/three/four/eight held requests
  for X/Y; verify the two/three boundary with actual official images and selected
  fields. This mechanics probe is separate from the four reconstruction cases.
- [x] Prepare a compressed source video only after validating reference identities,
  geometry, timing and independent replay parsing. Keep source controls/state
  outside the ingested video supplied to reconstruction.
- [ ] Establish native/rendered image agreement and the rendering/post-update
  phase relationship. The headless backend does not supply comparison pixels.
- [x] Validate a fifth source over 240..400 with consecutive short/full hops; extend
  source-only timer glyph coverage before candidate search, retaining initial failures.
- [ ] Expand beyond this stage/character pair, including combat, nonzero damage
  and stock changes. Horizontal motion and short/full hops are covered.
- [ ] Define video-reconstruction accuracy thresholds and broader visual metrics
  before claiming a successful reconstruction. Current criteria are benchmark gates.

Local benchmark: `.docker-state/local/runs/step-f4lpqe4n/analysis-final-v1/`.
All nine native/official scalar fields match bit-for-bit across 122 player-frames;
all seven common native observation fields match their recorded frames. The clip
has 61 timer-labelled frames at 60 FPS, without duplicate/missing labels. This is
selected-field equality for a controlled case, not complete-state/image parity.
Calibration uses ignored local game-derived images/templates and is explicitly
manual at bootstrap; it is not a general video-recognition system. See
[reference benchmark](reference-benchmark.md) for commands, policies and evidence.
The second source is in `.docker-state/local/runs/step-yanojpfn/analysis/`;
see [two-case evaluation](controlled-evaluation.md).

Acceptance: a reproducible benchmark can report where agreement holds, where it
fails, and what remains unmeasured. Full retail parity is not assumed or a reason
to postpone measuring a narrower supported case.

## 5. Video ingestion and observation extraction

- [x] Decode a short local progressive clip with original PTS/time base, dimensions,
  hashes and exact timestamps; retain variable spacing and identical adjacent PNGs.
  Reject missing/substituted PTS, rotation, interlacing and changing dimensions.
- [x] Support explicit decode intervals and manually reviewed gameplay crops,
  retaining original PTS, indices, source geometry and image hashes without resizing.
- [x] Download/inspect the supplied tournament opening and retain source-bound manual
  settings/timer evidence. No reconstruction result is claimed for this footage;
  see [tournament intake](tournament-video-intake.md).
- [ ] Detect cuts, missing game frames and unsupported gameplay segments. Ingestion
  explicitly leaves these unknown instead of deriving them from nominal FPS.
- [ ] Identify the gameplay region, stage, characters and player identities;
  separate overlays, HUD, camera motion and screen coordinates from world position.
- [ ] Align the clip timeline to candidate game frames, accounting for capture
  rate, pauses, speed changes and gaps instead of assuming one video frame per step.
  The fixed unpaused benchmark has inferred timer labels, explicit phase
  uncertainty and a PTS/game-clock check; general alignment remains open.
- [ ] Extract and track visible evidence: stocks, damage, fighter locations,
  actions and useful events. Represent occlusion and ambiguous observations explicitly.
- [x] Extend `Evidence` into an identity-bound manual timeline referencing decoded
  video frames/PTS, explicit game-frame alternatives, cue alternatives and unknowns.
- [x] Support manually reviewed action groups, facing, relative horizontal order
  and damage; retain individual manual timer readings and failed automatic labels.
- [x] Bind manually chosen fighter/stage image regions to source frames/hashes
  for direct rendered comparison. These are not detected roots or world positions.
- [ ] Measure observation accuracy against annotated controlled clips, including
  cases where the system should leave a value unknown.

Acceptance: a supported clip produces a reviewable observation timeline. The
first controlled manual timeline meets this boundary. Automatic gameplay
recognition and a general video observation system remain unimplemented.

## 6. Input and hidden-state reconstruction

- [x] Declare supplied known-start settings, seed/time base and neutral prefix,
  with provenance, for the first controlled search. These are not recovered from video.
- [ ] Infer or search genuinely unknown starting conditions, hidden state and RNG.
- [x] Compare coarse visual cues with simulated outcomes using explicit frame/value
  alternatives and unknowns. All cues at one sample must fit the same frame.
- [x] Refine all coarse-accepted candidates with a declared unshifted image-region
  objective; retain exact ties and separate patch-translation diagnostics.
- [ ] Add calibrated root/world-position/camera errors and broader objectives.
- [x] Search a declared finite grid over one short window using capture/restore.
  Retain every accepted alternative and do not claim unique original inputs.
- [x] Support ordered horizontal phases, including release and reversal, with
  strict bounds and the original single-change format. Rerun the whole selected
  program after checkpoint restoration and reproduce it from fresh boots.
- [x] Add explicit main-stick/button snapshots with press/hold/release semantics.
  Reject Start/pause before simulation, retain legacy formats and validate a jump.
- [x] Preserve measured input ambiguity: four distinct jump recordings tie on
  image evidence and produce identical official PNGs over the comparison interval.
- [x] Join consecutive windows by reproducing selected input history in fresh sessions
  and checking exact boundary observations and replay bytes before branching.
- [ ] Handle drift, conflicting observations and later-window failures with backtracking.
  The current workflow carries one rendered minimum and retains tie evidence.
- [x] Persist start recipe, candidate inputs, costs, traces, identities and chosen
  continuation. Search checkpoints remain session-local; failed searches export nothing.
- [x] Continue from completed selected windows across sessions and validate the joined
  trajectory from two fresh boots. Native process checkpoints remain session-local.
- [ ] Resume an unfinished candidate grid or automatically revisit earlier selections.
- [x] Export only the selected continuation; compare its observations/replay bytes
  against a fresh boot with only the chosen inputs and validate parsing/playback.
- [x] Select a closer controlled trajectory from supplied initial conditions and
  manual image evidence; verify the known source's nine state fields after selection.
- [ ] Define broader reconstruction/visual acceptance and recover trajectories
  from other clips, then automate observation extraction.

Local prototype: 21 schedules, five accepted alternatives and 27 known manual
cues satisfied. The selected inputs differ from the source; source/reconstruction
pixels and positions still differ for that coarse default. Rendered refinement
then ranks all five schedules using six source-only regions, reducing whole-clip
RGB RMSE from 24.22 to 5.29. Its selected continuation matches the source's nine
fields across 122 player-frames in a separate post-selection check. An intentionally
contradictory negative control rejects every schedule and writes no replay. See
[manual reconstruction](manual-reconstruction.md) and [rendered refinement](rendered-refinement.md).

The delayed-left follow-up uses the unchanged 21-schedule grid, image objective,
timer calibration and cue-alignment policy. Four schedules satisfy its 28 known
cues. Image evidence selects eight neutral steps after frame 239 followed by
stick X=-80; whole-clip RGB RMSE falls from 31.13 to 5.28. Its fresh recording
reproduces and plays in official Dolphin, and all nine known-source fields match
across 122 player-frames after selection. The new source-only annotations and
remaining limits are documented in [controlled evaluation](controlled-evaluation.md).

The third case searches 27 movement/release/reversal programs. Its corrected
timeline has 31 known and five unknown cues; initial overconfident turnaround
annotations and rejected searches remain retained. All 27 satisfy the coarse
cues, while the old single-change grid rejects every candidate and exports no
replay. Rendering the complete population selects candidate 13 and reduces
whole-clip RGB RMSE from 29.56 to 5.46. Nine source fields match across 122
player-frames after selection. A fresh rerun of the earlier delayed-left case
also produces the same accepted set and replay bytes. See
[phase reconstruction](phased-reconstruction.md).

The jump follow-up accepts eight of 24 X/Y/onset/hold programs. Image refinement
retains four exact minima: X or Y held for one or two requests at onset six. The
chosen continuation reduces whole-clip RGB RMSE from 25.98 to 5.55 and matches all
nine known-source fields across 122 player-frames after selection. All four ties
also match those fields and have 61 identical official PNGs despite distinct
recorded inputs. Earlier phase-search results and replay bytes remain unchanged.
See [button reconstruction](button-reconstruction.md).

A fifth controlled source joins two windows over frames 240..400. Eight first-
window and 16 second-window candidates pass coarse cues; all 24 are parsed and
actually rendered. Image ranking selects a short hop and then a full hop, with
four tied programs at each selection. The next session reproduces the selected
prefix state and replay bytes before searching. Two fresh joined boots, parsing
and official Playback pass; nine source fields match across 322 player-frames
only after selection. Whole-clip RGB RMSE is 5.47 without an absolute acceptance
threshold. See [consecutive windows](multi-window-reconstruction.md) for the
single host workflow, source calibration extension, exact scope and artifacts.

Acceptance: a known reference clip can be reconstructed within the predefined
error bounds, with uncertainty and failures reported. Exact original inputs and
hidden state are not required or claimed.

## 7. End-to-end reconstruction and review

- [x] Provide one host command connecting consecutive annotated-window search,
  genuine export, official rendering/ranking, prefix checks and joined replay review.
- [ ] Connect arbitrary video/YouTube ingestion and automatic observations to that
  workflow, with unknown-start recovery and general trajectory acceptance.
- [x] Parse the prototype's exported replay and run official Playback, with each
  result separate and failed timer-recognition evidence preserved.
- [x] Produce a controlled timer-aligned source/reconstruction clip and report
  coarse cue fit, pixel diagnostics, supplied settings, unknowns and limitations.
- [ ] Define/validate visual trajectory acceptance and support broader source clips.
- [ ] Allow corrections and reruns without replacing the original observations
  or claiming that an incomplete reconstruction covers the whole video.
- [ ] Distinguish clip-only partial recordings from complete games with real
  Game End events. Preserve that distinction in outputs and user documentation.

Acceptance: one supported short video can be processed into a playable `.slp`
and an honest comparison report using a documented reproducible workflow.

## 8. Broader evaluation and practical usability

- [x] Supply development diagnostics, bounded experiment commands, retained logs
  and native/Python component tests.
- [x] Evaluate a second controlled horizontal motion without changing the search
  grid, scorer or timer calibration. Validate fresh selected recording, parsing,
  actual official rendering and a separate post-selection source-state comparison.
- [x] Evaluate movement/release/reversal with a richer input grid and the existing
  image scorer/calibration. Preserve annotation revisions and failed attempts;
  this iterative development case is not a blind held-out evaluation.
- [x] Evaluate a jump using source-only annotations and unchanged scoring/calibration;
  independently validate recorded buttons and preserve four indistinguishable
  trajectories with different recorded inputs.
- [x] Validate a two-window short/full-hop sequence over 161 frames, including
  prefix reproduction, all accepted candidate renders and joined official review.
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

The latest Docker Python run passed **309 tests**. The current native build passed
**10 host/component and 23 game-library tests**; the unchanged independent parser's
last component run passed **9 tests**. Synthetic protocol/component tests
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
| Controlled native/official benchmark | Nine fields bit-exact across 122 player-frames; seven-field native observation check passes; `.docker-state/local/runs/step-f4lpqe4n/analysis-final-v1/result.json` |
| Labelled reference clip | 61 lossless frames at 60 FPS, game frames 240..300; `reference.mkv`, `frame-index.csv`, `frame-labels.json` in that analysis directory |
| Manual MP4 cue search | 21 candidates, five accepted alternatives, 27 known cues satisfied; `.docker-state/local/runs/step-8flqxuip/search-result.json` |
| Selected replay and official review | Fresh selected observations/replay bytes match; independent parsing and official progression pass; nine native/official fields match across 122 player-frames; `review/review-result.json` in that run |
| Source/reconstruction comparison | 61-frame `review/comparison.mkv`, source left/reconstruction right; 12 manually read source timers, pixel RMSE about 24.22/255 with no visual pass threshold |
| Failed-search negative control | Synthetic contradictory damage hypothesis rejects all 21 candidates; no replay exported; `.docker-state/local/runs/step-bx8m_rsb/search-result.json` |
| Rendered candidate refinement | All five genuine candidates parsed/captured; source-only regions select candidate 8; `.docker-state/local/render-refinement-v1/ranking/ranking.json` |
| Refined trajectory and verification | Fresh recording bytes/observations reproduce; known source's nine fields match after selection; `verification.json` in that ranking directory; fresh run `.docker-state/local/runs/step-rf5r43y0/` |
| Refined image review | 61-frame `review/comparison.mkv` in the fresh run; whole-clip RGB RMSE 5.29, also 5.29 on 58 unused clip frames; no visual acceptance threshold |
| Second source/reference | Genuine delayed-left recording, nine-field and timer checks pass; `.docker-state/local/runs/step-yanojpfn/analysis/result.json` |
| Second rendered refinement | Four accepted candidates actually rendered; candidate 13 selected; `.docker-state/local/render-refinement-v2/ranking/ranking.json` and `verification.json` |
| Second fresh selected replay/review | Reproduced replay, parser and official checks pass; whole-clip RGB RMSE 31.13 to 5.28; `.docker-state/local/runs/step-3b6dfqse/review/comparison.mkv` |
| Source preparation/default regression | Validated source MP4 preparation reproduces; original default replay remains byte-identical; `.docker-state/local/manual-case-v2/preparation-regression.json` and `legacy-recording-regression.json` |
| Two-case comparison | Nine source fields exact across 244 player-frames after selection; `.docker-state/local/manual-case-v2/evaluation-summary.json` |
| Third source/reference | Movement/release/reversal, nine-field and timer checks pass; `.docker-state/local/runs/step-ioh7k72a/analysis/result.json` |
| Phase search and single-change negative control | 27 phase candidates accepted; all 21 old single-change candidates rejected with no replay; `.docker-state/local/runs/step-ey2lbxpq/` and `step-eb7992zt/` |
| Complete phase refinement population | All 27 genuine candidates parsed/rendered and own native/official fields agree; candidate 13 selected; `.docker-state/local/render-refinement-v3/ranking/` |
| Fresh phase winner/review | Reproduced bytes/observations; nine source fields exact after selection; whole-clip RGB RMSE 29.56 to 5.46; `.docker-state/local/runs/step-ed588cpa/review/comparison.mkv` |
| Legacy search regression | Earlier delayed-left accepted set and selected replay bytes unchanged; `.docker-state/local/manual-case-v3/legacy-search-regression.json` |
| Jump source/reference | Genuine jump and native/official nine-field/timer checks pass; `.docker-state/local/runs/step-ubevmcm5/analysis/result.json` |
| Jump search and negative control | Eight of 24 accepted; all old horizontal candidates fail with no replay; `.docker-state/local/runs/step-pry0ri3g/` and `step-pc_e9ckc/` |
| Jump official refinement/review | All eight parsed/rendered; four exact image-score ties; fresh winner `.docker-state/local/runs/step-1cynkr0m/review/comparison.mkv`, RGB RMSE 25.98 to 5.55 |
| Jump input ambiguity | Four distinct replay hashes and input traces, 61 identical official PNGs, nine source fields exact; `.docker-state/local/manual-case-v4/recorded-buttons.json` and `ambiguity-evaluation.json` |
| Prior phase regression | Same accepted set and genuine replay bytes; `.docker-state/local/manual-case-v4/legacy-phase-regression.json` |
| Fox short/full-hop boundary | Ten real X/Y recordings: 1/2-request short hops and 3/4/8-request full hops; `.docker-state/local/fox-hop-boundary-v2/measurements.json` |
| Boundary official comparison | Two/three-request X runs each match nine fields across 122 player-frames; timer-aligned short-left/full-right clip; `official-analysis/` in that probe directory |
| Two-window source | Nine native/official fields exact over 322 player-frames and 161 timer labels; `.docker-state/local/runs/step-j0x10eav/analysis-expanded-clock/` |
| Timestamp-preserving windows | Original PTS/source identity retained; source-only annotations, calibration extension and frozen protocol in `.docker-state/local/manual-case-v5/` |
| Verified selected prefix | Second search reproduces first window boundary state and recording before capture; `.docker-state/local/runs/step-typtf91s/search-result.json` |
| Complete two-window workflow | All 24 accepted candidates parsed/rendered, exact ties retained; `.docker-state/local/joined-jumps-v1/result.json` and `window-*/` |
| Joined replay and review | Two fresh boots reproduce; actual official Playback and post-selection source checks pass across 322 player-frames; `joined/trajectory-verification.json` under that workflow |
| Joined comparison | 161-frame `joined/review/comparison.mkv`, whole-clip RGB RMSE 5.47; no visual acceptance threshold |
| Tournament source intake | 271 cropped frames with original PTS, visible settings and individual timer readings; `.docker-state/local/youtube-OWraeXAYElQ/` |
| Tournament setup/control probe | Yoshi's Story, Falco/Captain Falcon on P2/P3, four stocks/480 seconds; three restores and fresh branch bytes reproduce; `.docker-state/local/tournament-start-v1/probe-result.json` |
| Tournament setup official comparison | Nine fields exact across 842 player-frames (1..421), seven observation fields exact; `official-analysis/result.json` in that probe; no source-video reconstruction claimed |
| Default-match recording regression | New native build preserves prior two-jump replay SHA-256; `legacy-regression.json` in that probe |
| Pre-clock checkpoint/recording | Early pause -123; capture -40 while native counter is zero; both inputs affect negative frames; three restores/fresh bytes reproduce; `.docker-state/local/preroll-probe-v1/probe-result.json` |
| Playable pre-clock official comparison | Requested -39..140: nine fields exact across 360 player-frames; native observation mapping exact over all 528; `official-analysis-requested/result.json` in that probe |
| Strict Ready audit failure | Full -123..140 gate remains false: one Falco Y word differs at -113; original failed audit in `official-analysis/`, retained alongside requested-interval result |

The selected replay in both recording runs has SHA-256
`46b196b913b9a81bc501ddfcdd6f28c2710aabf665b0597d9059c9511e7e5dd2`.
Artifacts are ignored local evidence, not files guaranteed to exist in another
checkout. The complete selected recording has SHA-256
`5605bab19d66b2fdaaf0148ba924c5867fd9b17e3dd7b52f94c217856af1144b`.
The controlled benchmark establishes selected-field agreement only.
Manual search source/annotations are in `.docker-state/local/manual-case-v1/`,
with final PTS-preserving decode in `ingested-v2/`. Its coarse cue objective
passes, while `visual_reconstruction_accepted` remains false. The automatic
source timer coverage failure and individual manual readings are both retained.
The refined continuation passes the same checks and improves the image evidence;
its optional controlled-source state comparison is post-selection only. An
intentionally wrong reference fails verification without changing the ranking.
The second case retains its source-only annotations, frozen protocol identities,
five individual manual timer readings and automatic label failures in
`.docker-state/local/manual-case-v2/`. Neither case establishes an absolute visual
acceptance threshold. The 58 frames excluded from each region objective are
neighboring frames, and endpoints also have coarse cues; these are not independent
matches or a holdout from every pipeline stage.
The third case retains its initial/corrected manual timeline, source and five
manual timer readings in `.docker-state/local/manual-case-v3/`. Its 58 frames
excluded from region scoring likewise include some coarse cues and neighboring
motion. The jump's annotations, six manual timer readings and input-ambiguity
evaluation are in `.docker-state/local/manual-case-v4/`. Across all four selected
cases, nine fields match over 488 source player-frames; this is selected-field
evidence under supplied fixture conditions. Identical images among the tied jump
programs do not establish source MP4 pixel equality or complete game-state equality.
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
| `bd47d3e` | `18ded4f` | Official reference capture, timer-labelled clip and nine-field state comparison |
| `a9b3014` | `18ded4f` | MP4 ingestion, manual visual cues and bounded checkpoint search |
| `75333f4` | `18ded4f` | Rendered candidate refinement and post-selection source-state verification |
| `01409b0` | `18ded4f` | Second controlled motion and validated compressed-source preparation |
| `33af2bf` | `18ded4f` | Timed horizontal phases and movement/release/reversal evaluation |
| `7fc16a0` | `18ded4f` | Explicit button phases, jump reconstruction and measured input ambiguity |
| `5b557bc` | `18ded4f` | Fox short/full-hop measurement and actual official boundary comparison |
| `12f2c0e` | `18ded4f` | Consecutive annotated windows, verified selected prefixes and a joined 161-frame replay |
| `a0c8c6b` | `18ded4f` | Tournament footage intake with explicit crops and original timestamps |
| `d9bcfe6` | `14c13ea` | Tournament stage/ports/stock setup and 842-player-frame official comparison |

The complete timed-match follow-up pins engine `18ded4f`, published before its
parent gitlink update. It adds the missing completion callback and recording
status; the parent adds the complete-match experiment and stricter independent
parser/official frame-report checks.

The tournament setup follow-up used engine `14c13ea`; the current early-control
follow-up pins `b298efc`, published before the parent update. Setup adds Yoshi's
Story, physical ports and stock/countdown rules; early control covers negative
replay frames. The [setup](tournament-start.md) and [pre-clock](preroll-control.md)
probes remain separate from source-video reconstruction.

Changes are published to `houndsolo/yt2slp` on `main` and
`houndsolo/melee-unlocked` on `yt2slp/linux-headless`. See Git history for the
smaller setup and documentation commits. Earlier milestone test counts and
"unrun" results have been superseded by the current validation record above.
