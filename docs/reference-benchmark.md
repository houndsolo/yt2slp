# Controlled reference capture and state comparison

The first reference case compares the native simulation with **actual official
Slippi Playback 3.5.2 execution**, then retains a lossless, frame-labelled clip.
It does not infer native/Dolphin parity from parser acceptance or a file playing.
No game code, timing constants, math flags, engine ABI or playback binary is changed.

## Supported case and acceptance policy

This initial case is deliberately narrow:

- Fox/Falco, two human players, Battlefield, vanilla control session and the
  fresh game's two-minute timed rules. Requested RNG seed 1 and boot time base 0
  are configuration; actual recorded Game Start settings are exported separately.
- Boot with the existing native menu script, pause at the first match boundary,
  advance 240 neutral VI retraces, then 180 retraces with P1 stick X=80. All other
  axes/buttons remain neutral; ports 3/4 remain disconnected. There are no Start
  inputs, game pauses, restores, camera edits or alternate footage in this case.
- Compare the inclusive game-frame window **240..300**, containing 61 frames and
  122 player-frames. Every native boundary must report matching observation and
  recording frame counters. The engine still steps VI retraces, not an assumed
  universal one-to-one game-frame API.
- Require exact integer/float32 words for nine post-frame fields: action, X/Y
  position, facing, damage, shield, stocks, internal character ID and animation
  counter. Signed zero and even one ULP count as differences. Report maximum
  absolute error, RMSE, mismatch counts and the first difference separately.
- Require coverage for both players at every requested frame, matching exported
  settings, and no duplicate keys, invalid scalar words or non-finite values.
  There is no fitted frame shift, tolerance exception or dropped-frame repair.
- Separately compare the seven common native observation/post-frame fields at
  the same declared frame: action, stocks, animation, X/Y, damage and facing.
  Stage/character/shield equality is not claimed from the observation POD.
- Require exactly one labelled captured image per requested game frame, in
  chronological order, and exactly 61 output frames at 60 FPS. Missing,
  ambiguous, duplicated or reversed labels fail; no labels are interpolated.

These are **benchmark acceptance criteria**, not reconstruction accuracy
thresholds. Video-based state/input reconstruction and its error tolerances are
not implemented. Followers, other stages/characters, attacks, stock endings,
paused footage, unknown cameras, speed changes and arbitrary video remain outside
this first validated case.

## What the official executable exports

The installed executable's version and CLI were verified before using these
settings. Configuration behavior was inspected in official tag
[`v3.5.2`](https://github.com/project-slippi/Ishiiruka/tree/v3.5.2), commit
`bffe989d0bd3b83a4be3eaee708cf2755659e01e`:

- `Core/SlippiRegenerateReplays` and `SlippiReplayRegenerateDir` enable writing
  game-generated recording events during actual playback. The official
  `$Recommended: Slippi Recording` code is enabled in a private game profile.
  See [EXI_DeviceSlippi.cpp](https://github.com/project-slippi/Ishiiruka/blob/v3.5.2/Source/Core/Core/HW/EXI_DeviceSlippi.cpp).
- `Movie/DumpFrames`, `DumpFramesSilent`, `Settings/DumpFramesAsImages`, and
  `EFBScale=2` produce native-resolution PNGs. The PNG destination must exist.
  Menu and gameplay image dimensions can differ. See
  [RenderBase.cpp](https://github.com/project-slippi/Ishiiruka/blob/v3.5.2/Source/Core/VideoCommon/RenderBase.cpp)
  and [VideoConfig.cpp](https://github.com/project-slippi/Ishiiruka/blob/v3.5.2/Source/Core/VideoCommon/VideoConfig.cpp).
- The movie dumper excludes the request's start/end boundaries and can produce
  misleading startup/fast-forward counts. The frame-index OSD is not present in
  these dumps. Consequently neither AVI timestamps, PNG numbers nor the console's
  current-frame reports are used as image-to-game-frame labels. See
  [AVIDump.cpp](https://github.com/project-slippi/Ishiiruka/blob/v3.5.2/Source/Core/VideoCommon/AVIDump.cpp).

The capture command pads the requested window to 219..321, disables resync and
rollback display, checks contiguous official progress/file identity, and retains
all PNGs, regenerated events, request/configuration and stdout. Its initial
`capture_passed` result does **not** assert state agreement or image alignment.

## Rendered timer calibration and frame labels

The known unpaused countdown HUD provides a separate image label. The timer
layout is fixed for this case at 642x528. Menus at other dimensions remain
unlabelled. Expected timer strings come from pinned slippi-js's
`frameToGameTimer`, including its frame-to-centisecond conversion; they are not
computed by treating the displayed fractional digits as a frame count.

`scripts/calibrate_timer.py` builds a **local** glyph calibration from manually
verified timer strings on retained captures. The main clock and smaller
fractional digits have separate glyph sets. No game-derived font/template/image
is committed. Calibration retains source image hashes, annotations and geometry.
It must cover all ten fractional digits. A new machine/run can reuse a retained
calibration only when its tested geometry/font/settings apply, or create a new
calibration by verifying its own captured images.

Recognition extracts connected white glyphs (threshold 190), normalizes them to
24x36 masks, and compares them with the calibrated shapes. This version fixes
maximum normalized Hamming error at 0.12 and minimum next-digit margin at 0.015.
These are shape distances, not confidence probabilities.
Those limits were established on the exploratory calibration capture before the
fresh benchmark was analysed; they are not relaxed to make its result pass.
Unrecognized labels remain unknown. Automated frame labels are explicitly
**inferred** from the rendered timer, with matching error retained; the calibration
annotations are the manually verified source evidence.

The final `frame-index.csv` maps clip frame 0..60 to game frame 240..300, the
rendered timer and the original PNG filename. The label refers to the visible
HUD clock convention. Equality of the rendering instant with the post-update
state sampling instant is not established.

## Reproduce locally

Build/test with Docker; run official GUI capture on the host. See
[recording/playback setup](slippi-recording.md) for the executable path, AppImage
extraction when FUSE is unavailable, and host/Docker path mapping.

```bash
bash scripts/docker.sh build  # adds FFmpeg; no GPU/display needed for native runs
bash scripts/docker.sh setup
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/record_benchmark.py
# Substitute the run folder printed above in the following commands:
xvfb-run -a python scripts/capture_benchmark.py \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso /home/houndsolo/Documents/vanilla.iso \
  --replay .docker-state/local/runs/step-REPLACE/native.slp \
  --output .docker-state/local/runs/step-REPLACE/official
```

For the retained local calibration, use
`.docker-state/local/capture-probe-images2/timer-calibration.json` on the host
(`/work/.local/capture-probe-images2/timer-calibration.json` in Docker). It is
ignored and is not supplied by cloning the repository. To create another one,
write an annotations JSON with an `anchors` array. Each entry has `image` (PNG
path relative to the JSON) and `timer` (`mm:ss.SS`), verified visually. For example,
the retained calibration's anchors are:

| Captured PNG | Verified timer |
| --- | --- |
| `user/Dump/Frames/framedump_25.png` | `01:56.00` |
| `user/Dump/Frames/framedump_26.png` | `01:55.99` |
| `user/Dump/Frames/framedump_30.png` | `01:55.93` |
| `user/Dump/Frames/framedump_35.png` | `01:55.84` |
| `user/Dump/Frames/framedump_40.png` | `01:55.76` |
| `user/Dump/Frames/framedump_55.png` | `01:55.51` |
| `user/Dump/Frames/framedump_70.png` | `01:55.26` |
| `user/Dump/Frames/framedump_85.png` | `01:55.00` |

Those PNG numbers are **specific to that capture**, not reusable frame labels.
Inspect the images when making new annotations; do not copy numbers blindly.

```bash
# Example shape of an annotation; supply enough verified entries for all digits:
# {"anchors":[{"image":"user/Dump/Frames/framedump_25.png","timer":"01:56.00"}, ...]}
bash scripts/docker.sh run python scripts/calibrate_timer.py \
  --annotations .local/capture-probe-images2/timer-annotations.json \
  --output .local/capture-probe-images2/timer-calibration-NEW.json
bash scripts/docker.sh run python scripts/analyze_benchmark.py \
  --run .local/runs/step-REPLACE \
  --calibration .local/capture-probe-images2/timer-calibration.json
```

Analysis requires the independently pinned parser dependencies. If not already
installed, run `bash scripts/docker.sh run npm ci --prefix tools/slippi-parser
--ignore-scripts --no-audit --no-fund` as one shell command. The exporter omits
player names/accounts. The final image-processing path uses FFmpeg and Python;
Tesseract was explored locally but is not a required dependency.

Output directories must be new; failed attempts are preserved. Supply
`--output .local/runs/step-REPLACE/analysis-NEW` to retain a later analysis attempt.
Malformed input errors exit nonzero; coverage/state/label failures write a failing
result instead of manufacturing a passing clip.

## Retained validation — 2026-10-22

Native run: `.docker-state/local/runs/step-f4lpqe4n/`. Official capture is in
`official/`; final analysis is in `analysis-final-v1/`.

- Native replay SHA-256:
  `46b196b913b9a81bc501ddfcdd6f28c2710aabf665b0597d9059c9511e7e5dd2`.
  Inputs, every native observation, requested settings, host/game/ISO hashes,
  parser/tool versions and capture binary/system-file identities are retained.
- Official Playback regenerates a separate replay during emulation. Comparing
  its parsed fields with the native recording passes all **122 player-frames**
  and all **nine fields** in 240..300: zero bit mismatches, zero numeric errors,
  matching settings and complete coverage. This is field equality, not equality
  of the complete `.slp` bytes or complete game/host state.
- All seven common native observation/post-frame fields match at the declared
  frame keys. No phase shift was fitted to make this comparison pass.
- All 61 requested rendered timer labels are present exactly once and in order.
  Two non-calibrated menu-sized images remain unknown. The final clip is FFV1,
  642x528, **61 frames at 60 FPS**, with an explicit frame/timer/image sidecar.
- `analysis-final-v1/result.json`, `frame-labels.json`, `frame-index.csv`, and
  `reference.mkv` retain the result and alignment evidence. Earlier exploratory
  movie dumps and the first analysis attempt are not the final benchmark result.
- Docker checks pass: 137 Python tests, 10 host/component tests, 23 game-library
  tests and 9 parser tests. New tests reject one-ULP/signed-zero differences,
  missing/shifted/duplicate state coverage, absent settings, ambiguous labels,
  and missing/duplicate/reversed image labels.

The native backend is headless and supplies no reference image here. Native versus
Dolphin **pixel/visual equality is unmeasured**, as are full-state equality,
render/post-update phase equality, reconstruction accuracy and retail parity
outside these selected fields and this interval. Wider inputs/stages/characters
and cases with nonzero damage, combat or stock changes still need benchmarks.

## Second source and video preparation

`record_benchmark.py --case fox-falco-battlefield-left-delayed-v1` records a
second genuine source: 246 neutral steps followed by 74 steps with P1 stick
X=-80, through match frame 321. The default remains the original right-moving
case; a fresh default run produces byte-identical replay output. Both cases
are declared in `src/yt2slp/reference_cases.py` for source preparation, outside
the reconstruction/ranking path.

The second source passes the same state and image-label criteria. The helper
`scripts/prepare_reference_video.py` checks source replay/clip identities and
reference gates, independently parses the genuine replay, encodes an H.264 MP4,
and ingests its original timestamps. Source controls and post-frame state are
kept outside the ingested video. See [controlled evaluation](controlled-evaluation.md)
for commands and the unchanged-grid reconstruction results.
