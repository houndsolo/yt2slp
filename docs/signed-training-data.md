# Signed training frames and first overfit sanity check

The training pilot now includes the actual supplied replay's pre-clock opening.
Official Playback 3.5.2 labels **241 clean images at replay frames −60..180**.
After a bounded image/post phase audit, the paired dataset produces **211
31-frame windows**, with center-frame targets at −45..165. A longer V100 run
memorizes this training clip, including button edges. Held-out recognition,
native input adaptation and learned replay generation are still unvalidated.

The source remains `recordings/examples/Game_20260622T203533.slp`, SHA-256
`c13e36c0f079200b6f00e2b3bef22ffe1165cde23797325218509718d794b40f`.
It is an examined **training/development match**, not an unseen test.

## Why the three clocks need separate evidence

| Clock / artifact | Association established here |
| --- | --- |
| Playback console `[CURRENT_FRAME]` | Can be one frame ahead of the displayed image when initially paused. The first advance can settle that relationship. |
| Cyan `Frame: N` emulator UI | Independently read using exact local bitmap templates from literal visual annotations; every selected displayed step must advance by one. |
| Clean PNG dump | OGL flushes the previous pixel buffer on the next swap. The single new PNG belongs to the **previous displayed index**, not the latest console value or filename. |
| HUD timer | Independently crosschecks all **180 positive** frame labels. Its frozen 8:00 value cannot distinguish negative frames. |
| Video PTS | Decode index `i` has source replay frame `−60+i` and presentation time `i/60`. The MP4 has no timing interpolation, crop or fitted transform. |
| Replay labels | Separate effective/physical pre-frame controls and same-key post-frame targets; raw fields unavailable in the pinned parser remain masked. |
| Native VI requests | **Not calibrated by this experiment.** Converting replay controls into native PAD requests remains separate. |

Source inspection uses the official pinned
[`ConfigManager.cpp`](https://github.com/project-slippi/Ishiiruka/blob/bffe989d0bd3b83a4be3eaee708cf2755659e01e/Source/Core/Core/ConfigManager.cpp),
[`HotkeyManager.cpp`](https://github.com/project-slippi/Ishiiruka/blob/bffe989d0bd3b83a4be3eaee708cf2755659e01e/Source/Core/Core/HotkeyManager.cpp), and
[`OGL/Render.cpp`](https://github.com/project-slippi/Ishiiruka/blob/bffe989d0bd3b83a4be3eaee708cf2755659e01e/Source/Core/VideoBackends/OGL/Render.cpp).
The UI requires both `SlippiPlaybackDisplayFrameIndex` and
`OnScreenDisplayMessages`. Linux F10 pauses; period advances a frame. The
unmodified installed executable, ordinary game code and original math are used.
Emulation speed changes wall-clock pacing only. The UI index is absent from the
clean dumps and never enters the model's image features.

## Capture, state and phase checks

The isolated Xvfb capture retains every UI screenshot, single-step transition,
clean PNG, source/configuration identity and real regenerated replay. Unknown
glyphs, multiple/missing new PNGs, display-index gaps and changing console/display
relationships inside the wanted interval fail. No PNG-number offset is fitted.
The observed startup console/display difference is 1; it settles to 0 before the
wanted interval and remains fixed there.

The independent preparation audit passes:

- All **241 signed UI labels** reread exactly from retained screenshots.
- All **180 positive HUD labels** select the same PNGs as the OSD/PBO association.
- Original source versus actual regenerated official replay: all nine selected
  scalar fields exact across **482 player-frames** at −60..180.
- All **241 clean PNGs** are byte-identical to the corresponding images in the
  earlier continuous capture, including negative frames. The diagnostic capture
  therefore did not change those training images.

Seven visibly reviewed ground/air observations across both players and both
sides of frame 0 support the predeclared **zero image/post offset**. Adjacent
offsets −2, −1, +1 and +2 fail the same evidence. The scope is this clip's visible
takeoff/landing evidence, not full-state/image equality or universal renderer
parity. The separate native Ready discrepancy at −113 remains unresolved and
lies outside this −60..180 audit.

The first phase annotation failed: Fox's raised-foot pose at frame 15 was read
as airborne, although that pose does not establish the engine ground/air flag.
That reading is now **unknown**, with its failed audit retained. Falco is also
unknown at −24/−23 because the Go graphic occludes him. None of those uncertain
visual observations is relabelled to force agreement; replay supervision retains
the actual original flags. Falco's visible landing at 2 and takeoff at 21 supply
clear positive-clock phase boundaries.

The prepared MP4 SHA-256 is
`2bdcaa3f1ddb4e54c9162f6923a2242846c55908742dba6a1f4c9344410ee4f9`.
The paired manifest SHA-256 is
`4b4f55a50f50600a024e06d05d3882995a4e0957ee04cb7c151f0476720098af`.
Its `training_ready: true` means the declared **bounded phase/data audit** passed.
Old provisional preparations remain false. A self-declared label flag or changed
audit receipt cannot promote a dataset.

## Training result and limits

The frozen ResNet18 encoder and 917,364-parameter temporal head use the same
architecture, seed 1, batch size 8 and learning rate 0.001. Targets remain physical
button holds/edges, 17-bin effective axes, action and airborne state. Protocols
freeze the dataset identity and require at least **0.95** hold/press/release F1,
state accuracy and each axis's bin accuracy before accepting this memorization
sanity check. No held-out labels select weights, thresholds or schedules.

| Training budget | Hold / press / release F1 | Action / airborne accuracy | Minimum axis-bin accuracy | Sanity result |
| --- | --- | --- | --- | --- |
| 2,000 updates | 0.939 / 0.655 / 0.528 | 1.0 / 1.0 | 0.988 | Failed: extra button events despite low loss |
| 10,000 updates | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 | 1.0 | Passed the unchanged thresholds |

The longer run's loss falls **10.53435 → 0.000243**. Its 422 player-frame targets
contain 146 held-button positives and 19 press / 19 release positives; there are
zero false positives or false negatives at the fixed zero-logit threshold.
This establishes training-clip memorization, not recovery of unique physical
inputs from unseen images. Bin accuracy is not exact original float recovery.
The short earlier attempt and its failed acceptance report remain retained.
Whole-frame inputs still include the ordinary HUD timer, player-name display
and background animation. No ablation establishes which cues the model uses;
memorizing this clip does not itself establish gameplay-action recognition.
The independent emulator UI index is excluded from the model images.

The V100 loop takes about **79.64 seconds** for 10,000 updates, plus about three
seconds of encoder extraction. Peak process RSS is about **1.40 GiB**; the
PyTorch allocator reserves **204 MiB**, excluding driver/context memory. No DDR4
upgrade is needed for this measured pilot. Larger datasets need bounded loading
and separate memory/throughput measurements.

Next: freeze this model and assess another whole match. The reserved example
swaps Fox/Falco's physical ports, while the current head contract uses fixed
physical-port slots. Explicit roster conditioning or a documented character/port
mapping is needed before treating that as an equivalent-config evaluation.
Then improve held-out performance and validate the effective-control → native
VI/PAD adapter before claiming learned replay reconstruction.

## Reproduction

Host capture needs Xvfb, xdotool, ImageMagick `import` and Pillow. Calibration,
preparation, pairing and tests run in Docker. Start from a new output directory:

```bash
# Host: collect candidate UI screenshots, then visually annotate literal indices.
xvfb-run -a -s '-screen 0 1024x768x24' env PYTHONPATH=src \
  python scripts/capture_signed_frames.py \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso /home/houndsolo/Documents/vanilla.iso \
  --replay recordings/examples/Game_20260622T203533.slp \
  --collect-calibration --output .docker-state/local/NEW-anchors

# Annotation anchors: image path, literal integer frame, and a visual-review note.
# Collect all digits 0..9; the console counter is not a substitute for reading UI.
bash scripts/docker.sh run python scripts/calibrate_frame_index.py \
  --annotations .local/NEW-osd-annotations.json --output .local/NEW-osd-calibration.json

# Host: existing verified local calibration, fresh signed capture.
xvfb-run -a -s '-screen 0 1024x768x24' env PYTHONPATH=src \
  python scripts/capture_signed_frames.py \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso /home/houndsolo/Documents/vanilla.iso \
  --replay recordings/examples/Game_20260622T203533.slp \
  --osd-calibration .docker-state/local/NEW-osd-calibration.json \
  --first -60 --last 180 --output .docker-state/local/NEW-signed-capture

bash scripts/docker.sh run python scripts/prepare_signed_video.py \
  --replay recordings/examples/Game_20260622T203533.slp \
  --capture .local/NEW-signed-capture \
  --timer-calibration .local/example-reference-v1/timer-calibration.json \
  --phase-observations .local/NEW-phase-observations.json --output .local/NEW-signed-video
```

`NEW-phase-observations.json` binds literal visible observations to the source
replay, capture-index hash and individual clean PNG hashes; it declares zero
post offset and records occlusions/ambiguous observations as unknown. See
`training_phase.py` for the bounded evidence schema. Export supervised labels
with two frames of extra context at either end, then use
`scripts/build_training_pairs.py` and the [learning runner](../tools/learning/README.md).
Use the [remote CUDA environment](remote-training.md) for the longer experiment.

Local ignored evidence is under `.docker-state/local/learning-timing-v1/`:
calibration annotations/templates; `signed-capture/` and `signed-capture-v2/`
failed probes; `signed-capture-v3/` successful capture; `video/` failed phase audit;
`video-v2/` accepted video; `labels.json`, `pairs/`, both overfit protocols,
`overfit-2000/`, `overfit-10000/` and acceptance reports. Successful video/pairs
and both model runs are also retained on the V100 filesystem. Game images,
MP4s, replay outputs, local glyph masks and model/feature weights remain ignored.

Docker validation passes **392 Python tests** and **seven optional model tests**.
The unchanged parser suite last passed 15 tests. Native code/math is unchanged;
native suites were not rerun for this training-data milestone.
