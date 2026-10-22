# Two controlled video-reconstruction cases

Updated 2026-10-22. The second case changes the source motion from rightward to
delayed leftward movement. The existing input grid, cue uncertainty, image
objective and timer calibration are unchanged. Both selected genuine recordings
pass independent parsing, actual official Playback and separate post-selection
checks against their known sources.

This evaluates two manually annotated clips with supplied starting conditions.
It does not establish general reconstruction accuracy or recovery of unknown
state from arbitrary footage. No vision model or GPU training was needed.

## Results

Both sources use vanilla Fox/Falco on Battlefield, requested seed 1/time base 0,
the same boot recipe and the rendered game-frame interval 240..300. Each clip
contains 61 frames at 60 FPS. Search starts from a supplied neutral prefix and
checkpoint at frame 239, using the original 21-schedule grid.

| Source motion | Coarse matches | Image-selected continuation after checkpoint | Coarse whole-clip RGB RMSE | Refined whole-clip RGB RMSE | Other 58 frames RGB RMSE |
| --- | --- | --- | --- | --- | --- |
| Right | 5 of 21 | 2 neutral steps, then stick X=80 | 24.22 | 5.29 | 5.29 |
| Delayed left | 4 of 21 | 8 neutral steps, then stick X=-80 | 31.13 | 5.28 | 5.27 |

RGB errors use 8-bit channel units. The ranking objective remains equal-region
unshifted RGB MSE; whole-frame errors above are later review diagnostics. No
image/time/camera offsets are fitted. Exact ties are retained. The optional
patch-translation diagnostic is never applied to the score.

Each winner matches all nine known-source fields bit-for-bit across 122
player-frames after selection: **244 player-frames across the two cases**.
The selected fields include X/Y, facing, action, damage, shield, animation,
stocks and character. This does not measure complete memory equality.

The 58 frames exclude the three region-scoring times in each clip. They are
neighboring frames of the same motion; endpoints also have coarse cue
annotations. They are not independent matches or a holdout from every pipeline
stage. An absolute visual acceptance threshold remains undefined.

## What changed for the second case

`src/yt2slp/reference_cases.py` declares source generators used only by recording
and source preparation. The original default still records 240 neutral steps
followed by 180 rightward steps, through match frame 421. A fresh default run
produces the original replay SHA-256:
`46b196b913b9a81bc501ddfcdd6f28c2710aabf665b0597d9059c9511e7e5dd2`.

The new `fox-falco-battlefield-left-delayed-v1` source records 246 neutral steps
followed by 74 leftward steps, through match frame 321. It uses ordinary PAD
polling. No game code, timing, math, engine ABI or Playback executable changed.

The second source supplies new manual evidence, reviewed before rendering or
ranking its candidates:

- Five cue samples at decoded indices 0, 15, 30, 45 and 60, with 28 known cues
  and two explicit unknowns. The existing +/-1-frame alignment policy is unchanged.
- Six image regions: Fox and a top-platform edge at indices 15, 30 and 45.
  These are source-image rectangles, not segmentation or world coordinates.
- Five individually reviewed MP4 timer readings at indices 37, 39, 40, 41 and 42.
  Automatic recognition failures are retained; no thresholds were relaxed and no
  missing labels were interpolated.

The fixed protocol hashes in
`.docker-state/local/manual-case-v2/protocol.json` bind the grid, search,
timeline, image scorer, ranking/reconstruction scripts and calibration to parent
commit `75333f4`. Only the new source and its visual annotations change. The
original source capture used padding 20; the second source and candidate captures
use padding 0. The frozen comparison concerns the search/scoring/calibration
policy, not identical capture preroll.

Four schedules pass the second case's coarse cues: candidates 0, 5, 9 and 13.
All four genuine replays are independently parsed and actually rendered in
official Playback 3.5.2 with resync disabled. Their own native/official nine-field
and rendered-frame coverage checks pass. Candidate 13 is the unique image-score
minimum; its six diagnostic patch translations are all zero.

Fresh native runs reproduce the winner's observations and replay bytes. The
final review reuses candidate 13's actual official capture because its replay
SHA-256 matches exactly, retaining the capture origin and identity metadata in
`capture-reuse.json`. This is a recorded official execution, not a parser-only
playback claim. The selected replay SHA-256 is:
`1f4f2928e1d06876c5d4cea2a6135ba91579fd0e09ae2e75d45bb6b474a6351e`.

## Preparing another declared source locally

Build/test in Docker; run official GUI capture on the host. Docker `/work/.local`
maps to host `.docker-state/local`; host `.local` is a separate directory.
The executable below is the unchanged extracted official Playback AppImage,
used where FUSE is unavailable. See [playback setup](slippi-recording.md).

```bash
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/record_benchmark.py \
  --case fox-falco-battlefield-left-delayed-v1
# Replace step-REPLACE with the printed native run directory:
xvfb-run -a python scripts/capture_benchmark.py \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso /home/houndsolo/Documents/vanilla.iso \
  --replay .docker-state/local/runs/step-REPLACE/native.slp \
  --output .docker-state/local/runs/step-REPLACE/official \
  --first 240 --last 300 --padding 0
bash scripts/docker.sh run python scripts/analyze_benchmark.py \
  --run .local/runs/step-REPLACE \
  --calibration .local/capture-probe-images2/timer-calibration.json
bash scripts/docker.sh run python scripts/prepare_reference_video.py \
  --run .local/runs/step-REPLACE --output .local/source-NEW
```

The calibration is a local, manually verified artifact, not supplied by a clone.
See [reference capture](reference-benchmark.md) for its creation and criteria.
Destinations must be new; failed attempts remain preserved.

Source preparation requires passing native/official state, observation-phase
and image-label checks, exact replay/clip hashes, and the declared FFV1 geometry,
frame count and rate. It separately parses the genuine source replay through
its declared last frame and confirms these bounded sources have no Game End.
It encodes H.264 at CRF 18, ingests the MP4 and checks all 61 original relative
timestamps equal `i/60`. A complete end-to-end helper run reproduces the second
source MP4 SHA-256:
`d92c09cdffc8af72f2b880b429cf2d5e966fc923de8a1e1f89735962166a502d`.

`source-provenance.json` retains source identities and preparation commands.
Controllers and known-source post-frame state remain outside the ingested
`video.json`. Source preparation may validate the source against known state;
reconstruction/ranking read only its pixels and visual annotations, plus the
declared start hypothesis. Known-source state is used again only by the optional
post-selection verification command.

Continue with [manual cue/search preparation](manual-reconstruction.md) and
[candidate export/capture/ranking](rendered-refinement.md), substituting the new
video, annotations and output paths. The unchanged search specification is
`configs/manual-horizontal-search.json`. For the retained second case, these
inputs are in `.docker-state/local/manual-case-v2/`: `ingested/`, `timeline.json`,
`regions.json` and `manual-timers.json`.

## Retained evidence and checks

All paths below are ignored local artifacts, not committed game assets or files
guaranteed to exist in another checkout.

| Evidence | Host path under `.docker-state/local/` |
| --- | --- |
| Genuine second source and official reference checks | `runs/step-yanojpfn/analysis/result.json` |
| Source MP4, manual evidence, frozen identities and two-case summary | `manual-case-v2/` |
| Completed source-preparation rerun and parser/provenance | `manual-case-v2-preparation-check/` |
| Original default replay byte regression | `manual-case-v2/legacy-recording-regression.json` |
| Second coarse search and default review | `runs/step-dg52jgcx/` |
| All four candidate replays, official captures, ranking and verification | `render-refinement-v2/` |
| Fresh selected replay and source-left/reconstruction-right review | `runs/step-3b6dfqse/review/comparison.mkv` |
| First case's independent verification | `render-refinement-v1/ranking/verification.json` |

Docker GCC 14 checks pass: **196 Python, 10 host/component, 23 game-library and
9 independent parser tests**. New source-policy tests reject unsupported cases,
wrong replay/clip identities and incomplete validation gates. Real ISO runs
separately exercise source preparation, unchanged default replay generation,
checkpoint search, independent parsing and official rendering.

The [third controlled case](phased-reconstruction.md) extends the controller grid
to movement, release and reversal. Jump cases, broader combat and unknown-start
footage remain future work. Automatic observations,
camera/world-position recovery, multi-window search and arbitrary YouTube
reconstruction remain open. Neither successful case requires training a model.
