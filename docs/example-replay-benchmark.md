# Standardized benchmark from a supplied replay

Validated locally on 2026-10-23. This replaces further fitting of the YouTube
opening, whose starting platform was misidentified. The source is an actual
user-supplied replay, not a native-generated reference with known controller
programs. The first search is an approximation with a substantial motion mismatch.

## Source MP4 and spawn policy

Source: `recordings/examples/Game_20260622T203533.slp`, Fox costume 2 / Falco
costume 3, physical P1/P2, Battlefield, four stocks and eight minutes. Its SHA-256
is `c13e36c0f079200b6f00e2b3bef22ffe1165cde23797325218509718d794b40f`.
The replay contains 307 Gecko records, including the neutral-spawn hook at
`0x8016e510`. The source records UCF; native vanilla control does not implement
that full code configuration.

Neutral starts are a code-defined policy, distinct from ordinary per-port stage
starts. The [official neutral-spawn implementation](https://github.com/project-slippi/slippi-ssbm-asm/blob/ee0f9cbcd7d0442ef80eb85f942f8be234affd4d/External/NeutralSpawn/NeutralSpawn.asm)
uses spawn order, stage-specific coordinates and facing. Merely placing fighters
on opposite platforms is not general support for this code or its other effects.

For this particular Battlefield singles case, stage-point indices **2/3** give
the same initial layout. The native default P1/P2 starts are center/top and fail
the startup comparison. With explicit indices 2/3, seven fields match exactly at
both supplied initial boundaries **-123 and -40**: x, y, facing, action,
animation, stocks and damage. That is 28 scalar words across four player-frames,
not complete-state or code-set equality. No later source state or original
controller values were used to choose the input program.

Official Playback 3.5.2 renders from recorded frame -123 with resync disabled.
All 180 images for replay frames **1..180** have unique verified HUD labels.
`prepare_example_video.py` encodes those images into a **three-second MP4**, H.264
CRF 18, 642x528 at 60 FPS. It performs no crop, resize or fitted alignment. Ingestion
verifies all 180 timestamps, preserves image hashes, and keeps source controls and
later source state out of `video.json`. The MP4 starts after pre-clock gameplay;
the initial recipe/prefix is explicitly supplied, not inferred from that crop.

MP4 SHA-256:
`1f952cd9c3e75ab3d573e5f1d698c4ffd17a385acfc36a238bf076628f3771c9`.

Only after input selection, an independent state audit compared the original
source replay with its actual official regenerated events. **All nine fields
match across 360 player-frames (1..180)**. Thus this video source has a verified
playback reference; that result is separate from reconstruction accuracy.

## First video-derived search

The [64-program grid](../configs/example-opening-search-v1.json) combines eight
Fox neutral/movement/jump/shield hypotheses with eight Falco drop/laser/hop
hypotheses. It uses complete two-controller snapshots and checkpoint -40, running
58 VI requests to replay frame 18. Four source-MP4 images at decode indices
0/5/10/15 supply damage and horizontal order: 16 known cues, 16 unknown action/
facing cues, with the existing declared one-frame render/post phase uncertainty.

Two programs pass, **40 and 48**. Both genuine exports parse independently and
play in official Dolphin. Their own native/official nine fields match over
1..17 (68 player-frames total). Six source-only fighter/platform regions at
indices 0 and 10 are frozen before candidate-image inspection. The existing
equal-region unshifted RGB objective selects **48**, with no tie. No source
replay controller values or later posts enter ranking.

One automatic MP4 timer label is missing, at decode index 7. Its literal
`07:59.88` reading is individually observed, identity-bound and retained alongside
the failed automatic pass; thresholds are unchanged. Complete source/official
timer coverage and the MP4 PTS clock check then pass.

The selected program reproduces observations, signed recording keys and genuine
replay bytes from fresh boots. Independent parsing, a fresh official capture,
17-frame aligned comparison and ranking verification pass. Its SHA-256 is
`ce185274d0707e86281a799163003f395b587ac3b2c00981ca5d480fa4c102b7`.

**This is not an accurate recreation yet.** Whole-frame RGB RMSE is **54.02/255**;
the 15 neighboring frames outside the two fit images have RMSE **54.06**. The
source Falco descends to the main floor while this grid's minimum stays near the
side platform, changing the camera too. In the separate post-selection source
audit, x differs for all 34 player-frames, y for 29, action for 34, animation for
29, and damage for three. Facing, shield, stocks and character match. Unknown
actions and missing vertical/platform constraints allowed an inadequate grid
to satisfy the sparse cues. No absolute visual acceptance is claimed.

## Known setup gaps and next work

The source Game Start seed is **33480**. Supplying that value to the current
native RNG override records Game Start seed **1528088407**: the override runs at
item initialization, after Game Start recording. These are different boundaries.
Matching a seed number in configuration does not establish matching RNG state.
The benchmark retains this failed seed-boundary check; no header, events, math or
timing constants were rewritten to hide it.

Next work is to align the supported source code/start configuration and seed
boundary, then add explicit vertical/platform observations and input programs
that actually produce the observed descent. Extend the fitted interval only
after those gates improve. Full UCF/code-set compatibility, source hidden-state
equality and reconstruction of the entire three-second MP4 remain unvalidated.
Original source inputs remain outside the reconstruction interface. This is an
iterative development example, not an independent held-out match evaluation.

## Reproduction and artifacts

Native/preparation tools run in Docker; official capture runs on the Arch host.
Use new output directories to retain failures. Setup/code inspection exposes
only whitelisted fields; `--opening-state` explicitly supplies just -123/-40.

```bash
bash scripts/docker.sh run node tools/slippi-parser/inspect-settings.cjs \
  recordings/examples/Game_20260622T203533.slp --opening-state

xvfb-run -a python scripts/capture_benchmark.py \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso /home/houndsolo/Documents/vanilla.iso \
  --replay recordings/examples/Game_20260622T203533.slp \
  --output .docker-state/local/NEW-capture --first 1 --last 180 --padding 0 \
  --include-preroll --request-start -123

# With inspected setup JSON and a separately verified local timer calibration:
bash scripts/docker.sh run python scripts/prepare_example_video.py \
  --replay recordings/examples/Game_20260622T203533.slp \
  --settings .local/example-reference-v1/source-setup.json \
  --capture .local/example-reference-v1/source-capture \
  --calibration .local/example-reference-v1/timer-calibration.json \
  --output .local/NEW-video
```

Ignored host artifacts:

| Evidence | Path |
| --- | --- |
| Catalog, startup/seed checks, frozen source annotations and protocols | `.docker-state/local/example-reference-v1/` |
| Source MP4 / ingested images | `example-reference-v1/video/source.mp4`, `video/ingested/` |
| First search and selected genuine recording | `.docker-state/local/runs/step-k7ghpedn/` |
| Both official candidate captures | `example-reference-v1/candidates/` |
| Rejected automatic-clock pass / completed ranking | `example-reference-v1/ranking/`, `ranking-manual-clock/` |
| Fresh selected official review and lossless comparison | `.docker-state/local/runs/step-i9yqw5lf/review/` |
| MP4 comparison preview | `example-reference-v1/comparison-preview.mp4` |
| Separate original-source and reconstruction state audit | `example-reference-v1/post-selection/result.json` |

Abbreviated paths are under `.docker-state/local/`. Generated MP4s, SLPs, images,
glyph templates and state exports remain outside Git. The curated supplied
example remains tracked. Docker checks: **343 Python tests** and **12 parser/
preparation tests** pass. The native engine is unchanged from `5d283cc` with its
previous 10 host/component and 23 game tests.
