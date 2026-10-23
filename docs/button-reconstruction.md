# Button-driven jump reconstruction

Controller search now represents timed P1 main-stick and button samples, including
explicit release. This fourth controlled case evaluates X/Y jumping with the
existing image objective, timer calibration and supplied start. It does not add
automatic recognition, unknown-state recovery or multi-window search.

## Controller format

The original horizontal formats remain supported. The new format requires a
complete sample at every change:

```json
{
  "pad_phases": [
    {"start_after": 6, "stick_x": 0, "stick_y": 0, "button": 1024},
    {"start_after": 8, "stick_x": 0, "stick_y": 0, "button": 0}
  ]
}
```

Indices count zero-based VI input requests after the checkpoint. P1 is neutral
before the first change. Each sample stays held until the next change or window
end; release is explicit, not an automatic pulse or an inherited field. The
example holds X for two requests, then releases it. X is `0x0400`/1024 and Y is
`0x0800`/2048, as defined by the pinned SDK's `dolphin/pad.h`.

All four keys are required. Axes use signed-byte values and the button mask uses
the existing unsigned 16-bit PAD validation. Start (`0x1000`), including combined
masks containing Start, fails before simulation because this search requires
unpaused frame progression. Unknown fields, duplicate/unordered changes,
unchanged consecutive samples and changes outside the window fail explicitly.
The existing limits remain: 1..16 phases, at most 600 VI requests per window and
128 distinct candidate programs.

P2 remains neutral; ports 3/4 are disconnected. C-stick, analog triggers and P2
programs are not represented by this format. Actual reconstruction validation
in this milestone covers jump buttons with neutral axes. Other button masks and
vertical-stick actions have not been evaluated as reconstruction cases.

No game code, physics constants, math flags, ABI or timing changes are involved.
Ordinary PAD processing retains its latency. Search must still observe one
advancing match frame per VI for this controlled case; it never guesses an offset.
Selected-branch reruns, fresh boots, genuine recording and candidate export use
the same controller document.

## Fourth controlled source and evidence

`fox-falco-battlefield-jump-v1` keeps the existing vanilla Fox/Falco Battlefield
start, requested seed 1/time base 0 and clip interval 240..300. It records 244
neutral requests, two requests holding X and 74 neutral requests, ending at match
frame 321. Source controls and post-frame data stay outside ingested video and
the evidence used by reconstruction/ranking.

`configs/manual-jump-search.json` declares 24 hypotheses: onset 2/6/10, hold
duration 1/2/4/8 and X/Y. These are supplied search hypotheses, not controls read
from the source recording. The original cue vocabulary, +/-1-frame uncertainty,
timer thresholds and equal-region unshifted RGB MSE objective remain unchanged.

Manual source review supplies six samples at indices 0/15/22/30/40/60, with
25 known cues and 11 explicit unknowns. Spinning/landing poses, ambiguous facing
and overlapping horizontal roots remain unknown. Six source-only regions, chosen
before candidate simulation/rendering, cover Fox and a top-platform edge at
indices 15/22/40. Region rectangles do not measure roots or world coordinates.

The original 21 horizontal schedules all fail and export no replay. Eight of
the 24 jump programs satisfy the coarse cues: indices 0/1/2/3/8/9/10/11, covering
onsets 2/6, holds 1/2 and both buttons. Independent slippi-js parsing confirms
each exported replay contains its declared X or Y mask for exactly the requested
hold duration, including the distinction between one- and two-request holds.
Recorded button frames begin at 243 or 247; these are measured game recording
keys, not a change to the VI-request contract.

Source MP4 timer recognition leaves indices 37..42 unread. Their individual
visual readings are `01:55.39`, `01:55.37`, `01:55.36`, `01:55.34`, `01:55.32`,
`01:55.31`. The failed automatic result and identity-bound manual readings remain
retained. Thresholds are unchanged and labels are not interpolated.

## Local workflow

Use Docker for builds, native search and analysis. Official GUI capture runs on
the Arch host. Docker `.local` maps to host `.docker-state/local`; host `.local`
is separate. Start a new source with:

```bash
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/record_benchmark.py \
  --case fox-falco-battlefield-jump-v1
```

Capture/analyze the printed run and prepare its MP4 as in
[controlled evaluation](controlled-evaluation.md). A new source needs its own
manually reviewed, identity-bound annotations. For the retained fourth case:

```bash
bash scripts/docker.sh run python scripts/reconstruct_manual.py \
  --video .local/manual-case-v4/source/ingested \
  --timeline .local/manual-case-v4/timeline.json \
  --spec configs/manual-jump-search.json
```

Continue with [candidate export/capture/ranking](rendered-refinement.md), using
the printed search run, `.local/manual-case-v4/source/ingested`,
`.local/manual-case-v4/regions.json` and `.local/manual-case-v4/manual-timers.json`.
The eight accepted candidates fit the default export limit. Render the complete
population; no candidate may be omitted because its capture failed. Preserve
image-score ties and use declared order only to choose an export among tied
minima. Optional known-source state is evaluated only after selection by
`rank_candidates.py verify`.

## Validated result — 2026-10-22

All eight genuine candidate replays are independently parsed and actually played
in official Playback 3.5.2, with resync disabled and private profiles. Every
candidate passes its own nine-field native/official state comparison and complete
rendered timer coverage. Image evidence distinguishes onset timing but preserves
the exact button/hold ambiguity:

| Candidates | Onset after checkpoint | Holds | Buttons | Equal-region RGB RMSE |
| --- | --- | --- | --- | --- |
| 0/1/2/3, including coarse default | 2 | 1 or 2 requests | X or Y | 52.40 |
| **8/9/10/11, tied minima** | **6** | **1 or 2 requests** | **X or Y** | **8.78** |

Declared order selects candidate 8 for export: X held for one request. The source
generator held X for two requests; that original hold duration is not recovered
uniquely. Fresh native boots reproduce the chosen observations and genuine replay
bytes. Its actual official capture is reused by exact replay hash, with origin
metadata retained in `capture-reuse.json`.

Whole-clip RGB RMSE improves from **25.98 to 5.55**. The 58 frames excluded from
region scoring have RMSE **5.55**; some have coarse annotations and all are from
the same neighboring motion. They are not an independent-match holdout or a
holdout from every stage. No absolute visual acceptance threshold is established.

Post-selection comparison matches all nine known-source fields bit-for-bit across
122 player-frames. An additional post-selection ambiguity check establishes that
all four tied programs match those source fields and produce **61 byte-identical
official PNGs**, while their genuine replay hashes and independently parsed
physical button traces differ. Thus neither those rendered images nor the nine
fields distinguish the four inputs. This does not establish complete game-memory
equality or pixel equality with the compressed source MP4.

All four controlled selected cases now cover 488 source player-frames, under the
same supplied stage/character/seed/start conditions. No general video-to-replay
accuracy or unknown-state recovery is established by that count.

| Retained evidence | Host path under `.docker-state/local/` |
| --- | --- |
| Genuine source and official reference checks | `runs/step-ubevmcm5/analysis/` |
| MP4, source-only annotations, timer failures/readings, fixed protocol | `manual-case-v4/` |
| Coarse search and default review | `runs/step-pry0ri3g/` |
| Horizontal negative control, no replay | `runs/step-pc_e9ckc/` |
| All eight actual captures, ranking and verification | `render-refinement-v4/` |
| Parsed recorded button masks and durations | `manual-case-v4/recorded-buttons.json` |
| Post-selection evaluation of the four ties | `manual-case-v4/ambiguity-evaluation.json` |
| Fresh winner and source-left/reconstruction-right clip | `runs/step-1cynkr0m/review/comparison.mkv` |
| Prior multi-phase search/replay byte regression | `manual-case-v4/legacy-phase-regression.json` |

Selected replay SHA-256:
`0ef6e0c0796a8ed54e1cafc97db303aad686d2688f8475e0a5366969ee65bd32`.
Docker GCC 14 checks pass: **235 Python, 10 host/component, 23 game-library and
9 independent parser tests**. New tests cover X/Y hold/release, both main-stick
axes, full snapshots, invalid/missing fields, Start rejection, window bounds,
selected-branch restoration and legacy phase compatibility. The previous
movement/release/reversal search is also rerun against its real video and retains
the same accepted candidates and selected replay bytes.

Generated game material, recordings, images, annotations and clips remain ignored.
The next work is joining windows into longer trajectories and reducing manual
observation work; these remain unimplemented. No model training is required for
this controlled jump experiment.
