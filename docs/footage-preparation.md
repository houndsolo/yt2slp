# Workstation footage preparation for the expanded dataset

**Superseded deployment:** the user requested direct generation on the upgraded
V100 after connectivity returned. The current [server corpus pipeline](corpus-training.md)
plans 300 Fox–Fox/Fox–Falco Battlefield clips. The local experiment and failed
transfer below remain historical evidence; no workstation rendering is needed
for the new run.

The workstation can now render bounded clips from **later in a match**, using
official Playback 3.5.2 and the same exact per-frame UI/PNG audit as the signed
opening captures. This is footage preparation, not learned reconstruction.
Native game timing, physics and the model's training code are unchanged.

## Frozen selection

`select_footage()` uses `configs/learning-corpus-split-v1.json` without changing
its date groups or source membership. It selects all 34 training and 14
development-validation replays. The ten final-test replays are neither selected
nor opened. Multiple matches on one date retain that date's original split;
cross-date player disjointness remains unverified.

For each of 46 new clips, a content-hash rule chooses a 600-frame interval after
the first ten seconds, leaving two seconds before the recorded end. Positions
use only the frozen replay hash/end-frame metadata, not controls, later states
or model scores. The two audited original pilots retain their 241-frame clips.
The planned total is **28,082 images**, about 7.8 minutes: 20,041 training images
and 8,041 validation images. These are planned counts, not a completed dataset.

Only the original two selected replays are currently present on the workstation.
Fetching the remaining 46 sources from `prompter@10.12.0.10` failed: SSH first
refused the connection and subsequent bounded retries timed out. No replay or
footage transfer succeeded in this attempt. The server's existing starter
dataset, model/checkpoints and training controls have not been modified.

## Local validation completed

A new ten-second clip from the existing **validation** replay
`Game_20260623T163435.slp` covers frames **2400..2999**:

- All 600 retained UI labels and clean PNG associations pass the strict audit.
- HUD timers agree across the full interval. Automatic OCR misses two images
  during bright effects; literal visual readings of **07:18.61** and **07:18.41**
  fill only those unknown results. Original automatic failures are retained;
  thresholds are unchanged, and recognized readings cannot be overridden.
- Nine original/official post fields match exactly across 1,200 player-frames,
  without resync, a fitted frame offset or floating-point tolerance.
- The MP4 encodes/decodes to 600 frames at exact 60 Hz with unchanged geometry.
  Its image-only model view verifies all decoded image hashes. Controller labels
  are exported separately from the original replay.
- Image/post phase is explicitly transferred from the audited training pipeline;
  this clip does not have a separate manual phase-boundary review.

The playable local file is:

```text
.docker-state/local/vision-footage-v2/probe-midgame/video-manual/source.mp4
```

`probe-midgame/video/` retains the initial automatic-HUD failure.
`probe-midgame/hud-readings.json` binds the two literal readings to PNG hashes;
the successful audit is in `video-manual/frame-labels.json`. This probe remains
validation material and must not become a training example.

## Batch command and transfer boundary

After the missing selected replays have been copied into `recordings/examples/`:

```bash
PYTHONPATH=src LP_NUM_THREADS=2 python scripts/prepare_training_footage.py \
  --iso /home/houndsolo/Documents/vanilla.iso \
  --output .docker-state/local/vision-footage-v2 --jobs 2
```

Rendering runs locally in isolated Xvfb sessions with independent Dolphin user
directories. Audits, encoding and pinned parser exports run in GCC 14 Docker.
Two workers bound memory use; the command accepts one to four. Capture intervals
are bounded to 1,800 images and positive replay keys through 28,800. Playback
fast-forwards its genuine prefix before pausing ahead of each selected interval.
Every subsequent selected step still requires its exact UI label and single PNG.

`selection.json` freezes the full plan. `clips/<replay-sha>/clip.json` appears only
after that clip's video and labels pass. Completed clips are checksum checked
on resume, successful captures can be reused for preparation retries, and failed
attempts remain. The batch writes `footage.json` only when **all 48** pass.
Currently `status.json` is **incomplete**, with two reused pilot clips prepared
and 46 missing sources. No complete expanded manifest is published.

Unreadable timers fail preparation by default. An explicit literal-reading file
may be supplied at `manual-readings/<replay-sha>.json`; it must use the versioned
schema exercised by the probe, bind image hashes and include visual-reading notes.
It can fill only unknown OCR results. No neighboring timer or frame number may
supply a visual reading.

When SSH returns, finish local preparation, copy the footage/evidence to a new
ignored directory on the V100 with SCP, and verify file hashes after transfer.
The larger **feature dataset import and separate training configuration are
still pending**. The existing training runner's feature preparation selects one
match per date, so its old count fields alone cannot import all 48 clips. Do not
overwrite the starter dataset or resume its checkpoint with changed data.

All ISO/replay/video/image/label outputs stay outside Git. Docker checks pass
428 Python tests and 17 parser/preparation/export/catalog tests. Those checks
and the actual local validation clip establish the stated bounded behavior;
they do not establish the missing batch, feature import or recognition quality.
