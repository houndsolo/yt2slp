# First manual-cue input search

This prototype connects a short local MP4, manually sourced visual cues, native
checkpoint search, genuine recording and official Playback review. It finds
controller schedules consistent with **sparse categorical evidence**. It does
not yet reconstruct a measured position trajectory or accept a visual match.
No vision model is trained or required for this experiment.

## Supplied conditions and limits

The source is an H.264 MP4 made from the existing
[controlled reference clip](reference-benchmark.md), game frames 240..300. Fox
stands still, moves right, then goes offstage; Falco stands on the top platform.
The standard camera, two human players, vanilla Battlefield/Fox/Falco, seed 1,
boot time base 0, and a neutral prefix through frame 239 are **supplied fixture
conditions**, not facts recovered from pixels. Other rules remain fresh-game
defaults. The native session starts from a fresh match and simulates that prefix.

The committed [search recipe](../configs/manual-horizontal-search.json) lists
21 hypotheses: P1 neutral or left/right stick strengths, with several movement
onsets. After the onset, the axis stays constant through frame 301. P2 stays
neutral; other ports stay disconnected. This is one bounded window, using one
checkpoint. Unknown initial states, RNG inference, arbitrary inputs, joined
windows and cross-session search resumption remain unimplemented.

That recipe describes the original experiment. The same scripts now also accept
ordered horizontal phases for movement, release and reversal; see
[phase search](phased-reconstruction.md) for the format and third controlled case.
This still uses one checkpoint window and supplied starting conditions.

The solver reads the manual timeline, start recipe and ingested video identities.
It does **not** read the source replay, original controller trace, source replay
post-frame states or pixel-comparison result to score/select candidates.

## Video and observation contract

`scripts/ingest_video.py` uses Docker FFmpeg/ffprobe to retain one PNG per decoded
frame, its original integer PTS/time base, exact rational timestamp and file hash.
It requires increasing PTS, progressive video and fixed dimensions. Missing PTS,
rotation, interlacing, decoder timestamp substitution and unsupported dimensions
fail explicitly. Variable timestamp spacing and identical adjacent decoded PNGs
are recorded; frames are not duplicated to impose a nominal frame rate.
Gameplay cropping, cut detection, missing-game-frame detection and automatic
recognition remain unknown/unimplemented. This is local-file ingestion; obtaining
YouTube footage is a separate future adapter.

Manual samples bind to both the source video hash and the reviewed decoded image
hash. Each has explicit candidate game frames and `Evidence` values: observed,
inferred or unknown. Unknowns stay `null`, are retained and do not reduce cost.
Known cue values can have alternatives. Supported cues are:

- `action_group`: `idle`, `ground_locomotion`, `airborne`. These are coarse visual
  interpretations mapped to declared retail common action-ID sets, not exact
  animation/attack recognition. See `ACTION_GROUPS` in
  [timeline.py](../src/yt2slp/timeline.py) and the pinned engine's
  `sourceport/extern/melee/src/melee/ft/kinds/ftCommon/forward.h`.
- `facing`: left/right, inferred from the visible pose.
- `horizontal_order`: left/right of the other fighter. For this standard camera
  only, the objective interprets screen order as world-X order. This is not a
  camera solver or a pixel-to-world position calibration.
- `damage`: displayed integer damage, compared with floored/clamped simulated
  damage. Only zero damage is validated here; no stock cue is inferred from this
  timed-match HUD.

The retained timeline has five reviewed samples (decode indices 0, 10, 20, 40,
60), 27 known cues and three unknown cues. Fox's final pose/facing are unknown
because he is partly outside the picture; initial horizontal order is unknown.
Game-frame candidates are the verified visible countdown label plus/minus one
frame, explicitly allowing the unestablished rendering/post-update phase.
All cues at a sample must match **the same** candidate frame. Missing simulation
coverage fails; the solver cannot drop a cue or fit a convenient global offset.

Each violated known cue costs one. Acceptance requires zero violations. The
solver exhausts the declared grid, retains every trial/score/trace and every
accepted alternative, then deterministically selects the first accepted entry.
That policy does not identify the original inputs or rank equally compatible
inputs by probability. If none passes, it restores the checkpoint, saves the
failed report and exports no replay.

## Local workflow

All paths below assume the previous benchmark artifacts are available. Generated
footage, annotations, calibration, trial logs and replays stay ignored. A new
checkout must generate its own source/capture and manually review its images.

```bash
# Prepare a local fixture; choose a new directory for another attempt.
mkdir -p .docker-state/local/manual-case-v1
bash scripts/docker.sh run ffmpeg -v error \
  -i .local/runs/step-f4lpqe4n/analysis-final-v1/reference.mkv \
  -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p \
  .local/manual-case-v1/source.mp4
bash scripts/docker.sh run python scripts/ingest_video.py \
  .local/manual-case-v1/source.mp4 --output .local/manual-case-v1/ingested-NEW
```

Review decoded PNGs and create a timeline JSON. The following shows one sample's
shape; use actual hashes and reviewed values. The sample's alignment is supplied
evidence, not something ingestion automatically infers:

```json
{
  "schema": 1,
  "kind": "manual-visual-cues",
  "video_sha256": "COPY_FROM_VIDEO_JSON",
  "samples": [{
    "video_frame": 10,
    "image_sha256": "COPY_FROM_VIDEO_JSON_FRAME_10",
    "alignment": {
      "value": [249, 250, 251], "provenance": "inferred",
      "source": "Reviewed countdown label; allow one frame of phase uncertainty"
    },
    "cues": [{
      "player": 0, "field": "action_group",
      "evidence": {"value": ["ground_locomotion"], "provenance": "inferred",
                   "source": "Manual review of frames/000010.png"}
    }]
  }]
}
```

Then search in Docker and capture actual Playback on the host:

```bash
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/reconstruct_manual.py \
  --video .local/manual-case-v1/ingested-v2 \
  --timeline .local/manual-case-v1/timeline.json \
  --spec configs/manual-horizontal-search.json
# Substitute the printed run name. The replay ends at 301, so no extra padding:
xvfb-run -a python scripts/capture_benchmark.py \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso /home/houndsolo/Documents/vanilla.iso \
  --replay .docker-state/local/runs/step-REPLACE/selected.slp \
  --output .docker-state/local/runs/step-REPLACE/official \
  --first 240 --last 300 --padding 0
bash scripts/docker.sh run python scripts/review_manual.py \
  --run .local/runs/step-REPLACE --video .local/manual-case-v1/ingested-v2 \
  --calibration .local/capture-probe-images2/timer-calibration.json \
  --manual-timers .local/manual-case-v1/manual-timers.json
```

The search first restores/reruns its selected branch. It then boots a separate
fresh session with only the chosen inputs and checks selected observations and
complete replay bytes against that fresh recording. The independent parser and
official Playback are separate checks. A partial clip has no invented Game End.

## Manual timer readings and review

The unchanged local timer calibration left **12 of 61 compressed source images
unlabelled**. Its automatic coverage result remains a failure. All 12 timers were
individually read from retained image crops. Optional `--manual-timers` fills
unread labels with explicit source/image identities; it never interpolates,
changes thresholds or silently replaces a contradictory automatic label.

Manual timer JSON has `schema: 1`, `kind: "manual-timer-labels"`, `video_sha256`,
and `labels`, each with `video_frame`, `image_sha256` and `evidence`. The evidence
has an observed exact string such as `"01:55.98"`, `provenance: "observed"`, and
a source explaining which image was reviewed. These local readings and the
automatic failures are retained separately.

Review requires each requested timer label exactly once and in order in both
source and Playback images. It also checks source PTS against the unpaused 60 Hz
clock, allowing one source time-base tick without fitting a scale. It creates
`comparison.mkv` (source left, reconstructed official Playback right), an explicit
image mapping and whole-frame 8-bit RGB RMSE diagnostics. Compression, camera,
HUD and background differences are included. **No visual acceptance threshold
exists**, and coarse cue acceptance never becomes a claim of visual equality.

## Local evidence — 2026-10-22

Final run and review paths are recorded in [progress](progress.md). Results:

- 21 candidates, five accepted alternatives; selected P1 stick X=64 with zero
  neutral steps after the frame-239 checkpoint. The source used different inputs.
  All 27 known cues fit; three unknowns stay unscored.
- Restored selected continuation, fresh selected observations and fresh recording
  bytes agree. Selected replay SHA-256:
  `9e8c09ff8025d8473287012f3d6055776755a9e25a27c32526ad0bd0b9324a79`.
- Independent parsing accepts genuine contiguous events through frame 301.
  Official Playback 3.5.2 progresses through 239..301 with resync disabled.
  Nine selected native/official post-frame fields match bit-for-bit across 122
  player-frames in 240..300. This checks the chosen simulation against Playback,
  not against the original video's unobserved game state.
- Both rendered timelines cover 240..300; source coverage needs the 12 manual
  readings. The 61-frame, 60 FPS side-by-side clip exposes position/camera
  differences despite cue acceptance. RGB RMSE is about 24.22 on 0..255, a
  diagnostic with no pass threshold.
- An explicitly synthetic contradictory damage hypothesis rejects all candidates,
  saves its failed search and exports no `.slp`.

Follow-up: [rendered refinement](rendered-refinement.md) now uses manually chosen
fighter/stage image regions to rank all five candidates. It selects a closer
continuation and verifies the controlled source's nine state fields after
selection. The coarse results above remain retained evidence. World-coordinate
camera calibration, automatic observation extraction, general YouTube recognition,
hidden-state recovery, attacks/combat, long trajectories and trained models
remain future work.
