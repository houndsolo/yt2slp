# Refining input hypotheses with rendered video evidence

The first manual search left five input schedules consistent with coarse action,
facing, damage and ordering cues. This next stage renders **all five genuine
replays** in official Playback and ranks them using fixed source-image regions.
It selects a much closer trajectory for the controlled clip without training a
model, changing game math or inventing a pixel-to-world camera conversion.

This is a finite-candidate refinement with supplied starting conditions. It
does not solve arbitrary video, unknown initial state or unique original inputs.
Image-region error measures appearance/position/framing together; it is not a
fighter-root coordinate measurement or a calibrated camera model.

## Fixed evidence and objective

Six source-only rectangles were manually chosen before rendering/ranking the
complete candidate population: Fox and the left edge of the top platform at
decode indices 10, 20 and 40 (rendered game frames 250, 260 and 280).
The fighter regions provide pose/position evidence; stage regions provide
framing evidence. Each rectangle binds to the video/image hashes and a manual
source explanation. No foreground masks or world-position labels are inferred.

The policy is fixed as `equal-region-unshifted-rgb-mse-v1`:

1. Match source and candidate images by their visible countdown labels. Preserve
   the existing 12 manual source-timer readings and failed automatic labels.
   Require complete, ordered, unique frame coverage and the source PTS/clock check.
2. Decode original PNG dimensions into 8-bit RGB. Use the same rectangle in source
   and candidate, with no image translation, resizing, cropping to a better match,
   camera fit or time-offset fit.
3. Compute RGB mean squared error within each rectangle. Average the six region
   MSEs with equal region weights, so large regions cannot dominate by area alone.
   The reported region RMSE is the square root of that average, in RGB 0..255 units.
4. Rank every coarse-accepted candidate. Preserve exact rational ties and use
   declared candidate order only to select among tied minima. A missing replay,
   parser result, official capture, scalar agreement or rendered frame fails the
   refinement; it never becomes a best-of-whichever-candidates-finished result.

Separate patch diagnostics search integer translations within +/-8 pixels,
sampling every fourth pixel. They retain equal minima and flag boundary results.
Those shifts are **never applied** to the images or ranking objective. A best
patch shift is a local appearance diagnostic, not a measured character-root
error or confidence probability; scale/pose changes can affect it.

The solver reads source pixels, manual region/timer annotations and the declared
candidate population. The original replay's posts/controller trace are not
selection inputs. Optional known source state is evaluated only by the separate
`verify` command after the winner has been selected.

## Local workflow

Use the existing [manual search](manual-reconstruction.md) and its source video.
All paths below are retained local artifacts, not files supplied by a clone.
Native export/ranking/review run in Docker; official GUI capture runs on the host.
Source is `/work` in Docker; its `.local` maps to host `.docker-state/local`.

Create an ignored manual regions JSON. Its schema is:

```json
{
  "schema": 1,
  "kind": "manual-image-regions",
  "video_sha256": "COPY_FROM_VIDEO_JSON",
  "objective": "equal-region-unshifted-rgb-mse-v1",
  "translation_radius": 8,
  "regions": [{
    "name": "fighter-at-sample", "role": "fighter", "video_frame": 10,
    "image_sha256": "COPY_FROM_VIDEO_JSON_FRAME_10",
    "box": [332, 345, 76, 64],
    "source": "Manual review of the source image, before candidate ranking"
  }]
}
```

Supply at least one fighter and one stage region, each with a unique name and an
8-pixel diagnostic margin inside the image. Boxes are integer `[x,y,width,height]`,
8..128 pixels in size. Review actual source images; the example box is specific
to this local controlled capture and is not a detector for another clip.

```bash
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/export_candidates.py \
  --search .local/runs/step-8flqxuip \
  --video .local/manual-case-v1/ingested-v2 \
  --output .local/render-refinement-NEW
xvfb-run -a python scripts/capture_candidates.py \
  --candidates .docker-state/local/render-refinement-NEW \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso /home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/rank_candidates.py rank \
  --candidates .local/render-refinement-NEW \
  --video .local/manual-case-v1/ingested-v2 \
  --regions .local/manual-case-v1/regions-v1.json \
  --calibration .local/capture-probe-images2/timer-calibration.json \
  --manual-timers .local/manual-case-v1/manual-timers.json \
  --output .local/render-refinement-NEW/ranking
```

Export checks the native build/ISO/boot identities and reproduces every original
trial's selected observations before recording. Each replay is independently
parsed. Capture can reuse complete identity-bound jobs; incomplete jobs remain
preserved and fail explicitly. Export/ranking destinations must be new. Failed
ranking attempts retain diagnostics and publish no selected replay.

Ranking writes `selected.slp` using the chosen replay's genuine bytes, plus
`selected-spec.json`. Validate that specification through fresh native boots:

```bash
bash scripts/docker.sh run python scripts/reconstruct_manual.py \
  --video .local/manual-case-v1/ingested-v2 \
  --timeline .local/manual-case-v1/timeline.json \
  --spec .local/render-refinement-NEW/ranking/selected-spec.json
```

Use the printed run in the host capture and Docker review commands documented
in [manual reconstruction](manual-reconstruction.md). Then verify that its replay
hash matches the ranking, its fresh selected observations/bytes agree, and its
official Playback/state/frame coverage checks pass:

```bash
bash scripts/docker.sh run python scripts/rank_candidates.py verify \
  --ranking .local/render-refinement-NEW/ranking \
  --run .local/runs/step-REPLACE \
  --reference-state .local/runs/step-f4lpqe4n/analysis-final-v1/native-state.json
```

`--reference-state` is optional supplied ground truth for this controlled source.
It compares the nine selected fields after selection; it is never an argument to
`rank`. A supplied ground-truth mismatch writes a failed verification and exits
nonzero without changing the image ranking. For unknown footage, those true
source fields are unavailable and remain unmeasured.

## Validated result — 2026-10-22

Candidate exports/captures: `.docker-state/local/render-refinement-v1/`.
Ranking/verification: `ranking/ranking.json` and `ranking/verification.json`.
Independent fresh selected run: `.docker-state/local/runs/step-rf5r43y0/`.
Its source-left/reconstruction-right clip is `review/comparison.mkv`.

| Coarse candidate | Neutral steps after frame 239 | Then P1 stick X | Equal-region RGB RMSE |
| --- | --- | --- | --- |
| 3, previous default | 0 | 64 | 54.04 |
| 4 | 0 | 80 | 54.04 |
| **8, image-selected** | **2** | **80** | **9.63** |
| 12 | 4 | 80 | 52.07 |
| 16 | 8 | 80 | 62.58 |

- Candidate 8 is the unique minimum within this declared population. All six
  local patch diagnostics have zero best translation; no shifts were applied.
- Every candidate's nine selected native/official post-frame fields agree
  bit-for-bit across 122 player-frames. The winning fresh selected recording and
  observations reproduce, and official Playback progresses with resync disabled.
- Selected replay SHA-256:
  `0cd01b7a67235547d354ea5141c833858e257087315ac68f7a5312e4afb9d260`.
- Whole-clip RGB RMSE improves from the coarse default's **24.22 to 5.29**.
  On the **58 frames excluded from region fitting**, whole-frame RGB RMSE is
  **5.29**. These are neighboring frames of the same clip, not independent-match
  generalization. The two endpoint frames also have coarse cue annotations, so
  this excludes the region objective rather than every stage of the pipeline.
  Compression, camera, HUD and background effects are included.
- The optional source-state check, run after selection, matches all nine fields
  exactly in 240..300, including X/Y. This is a controlled-source trajectory check,
  not equality of complete game memory or recovery of source state from pixels.
- Docker checks pass: 186 Python, 10 host, 23 game-library and 9 parser tests.
  New tests cover source identities, invalid geometry, unshifted scoring, ambiguous
  patch matches, exact ties, equal region weights and incomplete populations.
- A deliberately wrong state reference fails verification and leaves the ranking
  unchanged; `ranking/negative-oracle-verification.json` retains that negative control.

There is no absolute visual acceptance threshold, trained model, automatic fighter
detector, camera calibration or unknown-state recovery yet. The chosen schedule
matches the controlled generator's schedule, but other unsearched inputs may be
visually equivalent. A second controlled clip with delayed leftward movement now
passes with the same grid, objective and timer calibration; see
[controlled evaluation](controlled-evaluation.md). A third
[multi-phase movement case](phased-reconstruction.md) uses an expanded controller
grid with this same image scorer. Jumps, combat and more informative/automatic
observations remain future work.
