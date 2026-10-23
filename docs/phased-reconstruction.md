# Reconstructing movement, release and reversal

The controller search now supports multiple timed horizontal phases within one
checkpoint window. It retains the previous single-change format and keeps the
game's ordinary PAD polling, math and timing. The later
[button extension](button-reconstruction.md) adds explicit jump press/release
programs. Unknown starting conditions and joined windows remain unimplemented.

## Phase format and bounds

Each candidate may use the original `{"start_after": 2, "stick_x": 80}` format
or a sequence of absolute change indices relative to the checkpoint:

```json
{
  "phases": [
    {"start_after": 2, "stick_x": 80},
    {"start_after": 18, "stick_x": 0},
    {"start_after": 26, "stick_x": -80}
  ]
}
```

In this example P1 is neutral for requests 0..1, holds right for 2..17, releases
for 18..25, then holds left for the rest of the window. Indices identify VI
input requests, not an assertion that game processing responds immediately.
P2 remains neutral and ports 3/4 disconnected.

Sequences contain 1..16 strictly increasing changes, all inside the bounded
window. Consecutive phases must change the axis. Values use the existing raw signed-byte
PAD validation. Unknown keys, unordered or duplicate changes, unsupported values
and phases outside the window fail explicitly. A window still has at most 600
VI requests and 128 distinct candidates.

Search restores the same process checkpoint before each candidate, then restores
and reruns the entire selected program. Genuine replay events from rejected
branches are discarded by the existing checkpoint mechanism. Fresh-boot
observation and replay-byte checks, independent parsing, candidate export and
rendered refinement all accept the same phase documents.

## Third controlled source

The declared source `fox-falco-battlefield-right-release-left-v1` uses the same
vanilla Fox/Falco Battlefield start, requested seed 1/time base 0 and clip window
240..300 as the [first two cases](controlled-evaluation.md). It records 240
neutral requests, 16 rightward requests, eight neutral requests and 56 leftward
requests, ending at match frame 321. Source controls and source state remain
outside the video and visual annotations consumed by search/ranking.

The new explicit grid in `configs/manual-phased-search.json` contains 27
programs: start delay 0/2/4, right duration 12/16/20 and release duration 4/8/12,
then held left. These are supplied hypotheses, not values recovered directly
from the video. The scorer, image objective, timer calibration and +/-1-frame
cue alignment policy remain unchanged.

Six source images at indices 0, 15, 24, 28, 50 and 60 provide manual cues. An
initial attempt overclaimed the turnaround's action/facing interpretation and
rejected all 27 candidates. Reinspection left three additional cues unknown:
action groups at 24/50 and facing at 28. A model's head direction during a turn
does not safely establish the game's facing word. The initial annotations,
failed searches, correction reasons and final 31 known/five unknown cues are
retained. This is an iterative controlled development case, not a blind holdout.

On the corrected timeline, the original 21 single-change hypotheses all fail and
export no replay. All 27 multi-phase hypotheses satisfy the coarse cues. Six
source-only regions, chosen before candidate rendering, compare Fox and a
top-platform edge at indices 15, 28 and 50. No source post-frame values are used
to select a winner.

The compressed source has five unread automatic timer labels. Individual visual
readings at indices 2/8/14/20/26 are `01:55.98`, `01:55.88`, `01:55.78`,
`01:55.68`, `01:55.58`. Failed automatic results remain preserved; calibration
thresholds are unchanged and labels are not interpolated.

## Local workflow

Use Docker for native operations and the Arch host for official GUI capture.
Docker `.local` maps to host `.docker-state/local`; host `.local` is separate.

```bash
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/record_benchmark.py \
  --case fox-falco-battlefield-right-release-left-v1
```

Capture/analyze the printed source run and prepare its MP4 as documented in
[controlled evaluation](controlled-evaluation.md). Inspect the new source images
to create identity-bound cue, region and any needed manual timer documents; the
retained local annotations are not a detector or labels for a different video.
For the retained third case:

```bash
bash scripts/docker.sh run python scripts/reconstruct_manual.py \
  --video .local/manual-case-v3/source/ingested \
  --timeline .local/manual-case-v3/timeline.json \
  --spec configs/manual-phased-search.json
# Replace step-REPLACE with the printed search run:
bash scripts/docker.sh run python scripts/export_candidates.py \
  --search .local/runs/step-REPLACE \
  --video .local/manual-case-v3/source/ingested \
  --output .local/render-phased-NEW --max-candidates 32
xvfb-run -a python scripts/capture_candidates.py \
  --candidates .docker-state/local/render-phased-NEW \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso /home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/rank_candidates.py rank \
  --candidates .local/render-phased-NEW \
  --video .local/manual-case-v3/source/ingested \
  --regions .local/manual-case-v3/regions.json \
  --manual-timers .local/manual-case-v3/manual-timers.json \
  --calibration .local/capture-probe-images2/timer-calibration.json \
  --output .local/render-phased-NEW/ranking
```

Validate the selected specification through fresh boots, then capture/review and
run post-selection verification as in [rendered refinement](rendered-refinement.md).
Known-source state, when available, is an optional argument only to `verify`.
Destinations must be new; failed attempts and their diagnostics are preserved.

## Validated result — 2026-10-22

Every one of the 27 genuine candidates is independently parsed and actually
executed in official Playback 3.5.2 with resync disabled. Private capture profiles
allow three independent captures at a time. The complete population passes each
candidate's nine-field native/official comparison and rendered timer coverage.
The winner is the unique image-score minimum in this declared grid:

| Candidate | Phase changes: request index / stick X | Equal-region RGB RMSE |
| --- | --- | --- |
| 0, coarse default | 0/80, 12/0, 16/-80 | 57.05 |
| 12, next closest | 2/80, 18/0, 22/-80 | 34.03 |
| **13, selected** | **2/80, 18/0, 26/-80** | **9.52** |

All six selected patch diagnostics have zero best translation; none is applied
to the objective. Fresh native sessions reproduce the winner's observations and
replay bytes. Review reuses its actual official capture by exact replay SHA-256,
retaining the origin in `capture-reuse.json`. Whole-clip RGB RMSE improves from
**29.56 to 5.46**; the 58 frames excluded from region scoring have RMSE **5.46**.
Those frames include some coarse annotations and neighboring motion, so they
are not an independent holdout from the entire pipeline. No absolute visual
acceptance threshold is established.

Only after selection, all nine known-source fields match bit-for-bit across
122 player-frames in 240..300. This is selected-field equality, not complete
memory/image parity or unique identification of original controls. The three
controlled cases together cover 366 source player-frames under the same supplied
stage/character/seed/start conditions.

| Retained evidence | Host path under `.docker-state/local/` |
| --- | --- |
| Genuine source and validated official reference | `runs/step-ioh7k72a/analysis/` |
| MP4, initial/corrected cues, regions, timer readings, fixed protocol | `manual-case-v3/` |
| Initial phase search rejected by overconfident cues | `runs/step-az1f6_hh/` |
| Corrected phase search and coarse review | `runs/step-ey2lbxpq/` |
| Corrected single-change negative control | `runs/step-eb7992zt/` |
| All candidate captures, ranking and post-selection verification | `render-refinement-v3/` |
| Fresh winner and source-left/reconstruction-right clip | `runs/step-ed588cpa/review/comparison.mkv` |
| Earlier left-case search/replay byte regression | `manual-case-v3/legacy-search-regression.json` |

Selected replay SHA-256:
`50b51f93ff00dfd62d979fc3bbe77d137892382d360ab95098c0672c4f67125e`.
Docker GCC 14 checks pass: **212 Python, 10 host/component, 23 game-library and
9 parser tests**. New tests cover phase boundaries, release/reversal, document
round trips, malformed programs, window bounds, selected-branch restoration and
legacy grid compatibility. An actual rerun of the previous delayed-left search
also preserves its accepted candidates and selected replay bytes.

Generated game material, recordings, clips, images and annotations remain ignored.
The [fourth case](button-reconstruction.md) now evaluates a button-driven jump.
Multi-window search and more automatic observations remain future work.
