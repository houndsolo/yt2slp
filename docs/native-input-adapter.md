# Measured native input timing and controlled inverse

The first input-adapter calibration passes. This establishes a bounded route
from **known recorded controls back to native PAD requests**. It does not yet
connect model predictions to generated gameplay. Native game code, physics,
floating-point flags and VI timing are unchanged.

## What was measured

The GCC 14 Docker run uses engine `fba2f21`, host API 21, the user's vanilla ISO,
the ordinary VS boot script and default Fox/Falco Battlefield setup. Physical
ports are zero-based. Scalar response is tested on ports 0/1; timing markers are
also tested on ports 1/3 and during playable Go pre-clock frames.

There are 245 independently parsed genuine probe recordings: staggered button/
stick timing markers, four stick-axis sweeps, two trigger sweeps, eleven
individual buttons, one/two/three-request X holds, alternate physical ports and
pre-clock markers. Each scalar pulse lasts six requests with neutral margins.
Scalar results require identical steady samples at three positions on both
ports. Start is excluded because it changes pause state.

Each request logs the signed replay key **before** and after a VI step. For all
measured timing channels, a request submitted while the latest recorded key is
`f` first appears in the recording at **`f + 2`**. For example, X submitted after
key 245 appears at 247. Candidate lags 0..4 are compared over the same interval;
exactly one must match. Missing labels or ambiguous markers fail. This measures
the existing control boundary; it does not change game timing or fit a state/
image offset. It is not a universal latency claim for hitlag, respawn or pause.

## Raw PAD values are not replay effective axes

Representative positive scalar samples from the generated profile:

| Channel | Raw PAD value | Recorded effective value (rounded here) |
| --- | --- | --- |
| Main/C-stick, single axis | 0, 8, 16 | 0 |
| Main/C-stick, single axis | 23 | 0.2875 |
| Main/C-stick, single axis | 24 | 0.3 |
| Main/C-stick, single axis | 40 | 0.5 |
| Main/C-stick, single axis | 80, 127 | 1 |
| Analog L/R alone | 41, 42 | 0 |
| Analog L/R alone | 43 | 0.307142854 |
| Analog L/R alone | 80 | 0.571428597 |
| Analog L/R alone | 128 | 0.914285719 |
| Analog L/R alone | 140, 255 | 1 |

The profile stores exact parsed float32 values, rather than the rounded table.
`exact_single_axis_pad()` accepts only an exactly observed scalar value.
`axis_candidates()` returns only measured raw candidates for a declared 17-bin
target. The sweep has no realization in stick bins 7/9 or analog-trigger bins
1..4. Missing bins raise an error; they are not silently mapped to zero. This is
coverage of this sweep, not a proof about every joint input/code configuration.

In the individual-button probes, digital L/R each force effective trigger 1 and
a derived `0x80000000` bit.
Z produces effective `0x80000110` and trigger about 0.35: copying effective
button bits directly into physical PAD buttons would therefore be wrong.
The expanded original-label audit confirms Z takes priority when combined with
L/R; see [sequence training](sequence-training.md). This is separate from a
native inverse calibration for compound controls.
Simultaneous diagonal axes, C-stick combinations and digital/analog shoulder
composition still need joint calibration and a wider decoder.

Fox's holds reproduce the earlier result: one/two requests give a short hop
(height about 10.65, initial vertical velocity about 2.10); three give a full
hop (height about 31.28, velocity about 3.68). All have three jump-squat frames.
These are native game coordinates, without a camera fit.

## Inverse, checkpoint and actual playback checks

`decode_controlled_row()` deliberately accepts only known physical A/B/X/Y plus
one cardinal main-stick axis, with neutral C-stick/triggers. It rejects unknown
labels and unsupported combinations. It does not reconcile the model's separate
hold/press/release heads or implement a general learned decoder.

Five fresh-boot inverse runs recreate the timing-marker recording, all three
hop recordings and the pre-clock recording **byte for byte**, using parsed
source controls and the measured phase. The final two requests are explicitly
neutral drains in this controlled source protocol; arbitrary missing predictions
are never filled that way. Repeating the original marker branch after all
checkpoint restores also gives the original replay bytes, excluding discarded
probe branches from its recording.

Official Playback Dolphin **3.5.2** actually played four inverse recordings,
with resync disabled and requests starting at -123. Playback-regenerated replays
were independently parsed and compared at the original signed frame/port keys:

| Case | Compared interval | Player-frames | Effective controls | Nine post fields |
| --- | --- | --- | --- | --- |
| Staggered markers | 241..276 | 72 | Exact | Exact |
| Two-request short hop | 241..336 | 192 | Exact | Exact |
| Three-request full hop | 241..336 | 192 | Exact | Exact |
| Playable pre-clock markers | -37..-3 | 70 | Exact | Exact |

Across 526 player-frames, effective buttons, main/C-stick X/Y and trigger match
exactly; x/y, facing, percent, shield, animation, action, stocks and character
also match. Floats are compared by float32 words, with no tolerance or fitted
offset. This is stronger than parser acceptance, and remains a selected-field
check rather than full-state or image equality.

**Playback's regenerated physical button fields do not preserve the source
PAD buttons.** Their mismatch counts are respectively 24, 2, 3 and 24
player-frames, while effective controls and the selected gameplay fields agree.
The verifier reports physical diagnostics separately. Use original recordings
for physical-button training labels; do not substitute these regenerated labels.
No source tournament-code/UCF parity or learned reconstruction is established.

## Reproduce and inspect

The current workstation artifacts are ignored:

- `.docker-state/local/native-pad-calibration-v5/`: requests, genuine probe and
  inverse `.slp` files, parser labels, profile and result. Profile SHA256 is
  `1676fead0d116e1771528cbf6ddb2e9f311863061758de87fe9dd4a71f348ea4`.
- `.docker-state/local/native-pad-official-v1/`: actual captures, regenerated
  recordings and `clock-v5-verification.json`, `hop-2-v5-verification.json`,
  `hop-3-v5-verification.json`, `preroll-v5-verification.json`.
- Earlier calibration versions and the first failed display launch are retained.

Profiles bind the host/game binaries, ISO, boot script, calibration/adapter code
and parser wrapper by hash. Verification binds the precise source replay,
capture and regenerated replay. Existing positive captures may be reused only
when their source replay hashes match the current inverse bytes.

With the native GCC 14 artifacts already built, use a **new** output directory:

```bash
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/calibrate_native_inputs.py \
  --output .local/native-pad-calibration-new
```

Official GUI capture runs on the Arch host (or the separately configured render
container), using the verified Playback AppRun, not Netplay. Example pre-clock
capture, again into a new directory:

```bash
xvfb-run -a -s '-screen 0 1024x768x24' env PYTHONPATH=src \
  python scripts/capture_benchmark.py \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso "$YT2SLP_ISO" \
  --replay .docker-state/local/native-pad-calibration-new/roundtrip-clock-preroll.slp \
  --first -37 --last -3 --padding 0 --include-preroll --request-start -123 \
  --output .docker-state/local/native-pad-official-new/preroll --timeout 120
bash scripts/docker.sh run python scripts/verify_pad_calibration.py \
  --calibration .local/native-pad-calibration-new \
  --capture .local/native-pad-official-new/preroll --case clock-preroll \
  --output .local/native-pad-official-new/preroll-verification.json
```

The calibration result intentionally says `official_playback_validated: false`:
actual Playback evidence belongs to the separate verification reports. Assets,
profiles, images, logs and generated recordings remain outside Git.

## Next integration work

1. Build/smoke-test the native engine on the V100 using GCC 14 Docker. Training,
   ISO and official rendering are already server-local; native simulation is not
   yet validated there. Leave an active training run unchanged.
2. Add a declared decoder for learned logits: reconcile held/press/release
   constraints, represent ambiguous/unmeasured axis bins and calibrate joint
   inputs. Preserve alternatives for timing refinement.
3. Bind the benchmark's initial setup, seed, prefix and relevant codes. Signed
   control targets need lookahead for the measured PAD boundary, plus explicit
   prefix/tail handling. Unknown controls must stay unknown or become declared
   hypotheses.
4. Feed image-only proposals into native checkpoint branches, refine timing and
   compare rendered candidates. Keep the source replay's later controls/state out
   of selection; score them only after selection.
5. Export the selected genuine replay, validate actual official playback and
   render source/reconstruction gameplay side by side. Current saved-model review
   videos still show source footage with control panels.
