# Fox short-hop/full-hop boundary

Measured 2026-10-22 with the unchanged native game and official Playback 3.5.2.
For an uninterrupted button jump from this standing Fox start, holding X or Y
for **one or two requests produces a short hop**; holding for **three, four or
eight produces a full hop**. The three-frame boundary is explicitly tested.

Both jumps have the same three-frame squat and take off together. The trajectory
diverges at takeoff, rather than in squat duration:

| Measured quantity | Short hop, 1/2 held requests | Full hop, 3/4/8 held requests |
| --- | --- | --- |
| Jump-squat game frames | 247..249, three frames | 247..249, three frames |
| First airborne game frame | 250 | 250 |
| Initial native Y velocity | 2.10 | 3.68 |
| Maximum root height above floor, game units | 10.65 | 31.28 |
| First maximum-height frame | 259 | 265 |
| First Landing action frame | 271 | 285 |
| Frames from takeoff to Landing action | 21 | 35 |

Values describe the supplied vanilla Fox/Falco Battlefield start, neutral axes,
requested seed 1/time base 0 and no interrupts. Height is game-root Y relative
to its starting floor Y, not sprite height or a pixel-to-world estimate. Velocity
comes from native observations; the official nine-field comparison does not
contain velocity. Positions match official playback bit-for-bit over 240..300,
including both apices and landing frames.

## Release timing and reconstruction

The pinned game's `ftCo_KneeBend_Enter` initializes `is_short_hop` to false.
`ftCo_KneeBend_Check_ShortHop` latches it true when both jump buttons are released
during a button-initiated squat. Jump entry then uses the corresponding vertical
initial velocity. See the local
[jump-squat source](../third_party/melee-unlocked/sourceport/extern/melee/src/melee/ft/kinds/ftCommon/ftCo_KneeBend.c)
and [jump source](../third_party/melee-unlocked/sourceport/extern/melee/src/melee/ft/kinds/ftCommon/ftCo_Jump.c).
No hop rule was inserted into our search or game physics.

Independent parsing confirms a two-request X hold on recorded frames 247/248,
released on 249 while still in squat. The three-request hold covers 247/248/249,
released on takeoff frame 250. X and Y have matching measured native fighter
trajectories within each class: all 1/2-request traces match, and all 3/4/8-request
traces match. Their actual recorded button events remain distinct.

Request indices remain separate from game-frame keys: onset is request six
after the frame-239 checkpoint, with ordinary PAD processing unchanged. There
is no fitted frame offset.

The [earlier four-way tie](button-reconstruction.md) consists entirely of short
hops. It does not mean short and full hops are indistinguishable. Its 4/8-request
full-hop hypotheses were rejected by the short-hop clip's coarse cues; this probe
now covers the missing three-request boundary directly.

Both modes use the same JumpF action ID here. Useful video evidence is the
vertical arc relative to the stage, apex timing and return to the floor, rather
than that action ID or `airborne` alone. Camera motion must remain separate from
root movement. Current fighter/stage image regions compare the rendered
difference without assuming world coordinates or training a vision model.

## Reproduce and review

Use Docker for measurement/analysis and the host for official GUI capture.
Docker `.local` maps to host `.docker-state/local`; host `.local` is separate.
Use new output directories.

```bash
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/measure_fox_jumps.py \
  --output .local/fox-hop-NEW
# Capture each boundary case on the host, substituting 02 and 03:
xvfb-run -a python scripts/capture_benchmark.py \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso /home/houndsolo/Documents/vanilla.iso \
  --replay .docker-state/local/fox-hop-NEW/hold-02-X/native.slp \
  --output .docker-state/local/fox-hop-NEW/hold-02-X/official \
  --first 240 --last 300 --padding 0
# Repeat the capture with hold-03-X, then:
bash scripts/docker.sh run python scripts/analyze_fox_jumps.py \
  --measurements .local/fox-hop-NEW \
  --calibration .local/capture-probe-images2/timer-calibration.json
```

The calibration is a local manually verified artifact, not supplied by a clone;
see [reference capture](reference-benchmark.md). Analysis requires matching
replay/ISO identities, exact nine-field native/official agreement, seven-field
native-observation agreement and complete timer labels before writing the clip.
It does not use PNG order as a frame label or infer hop height from hold duration.

Retained evidence is under `.docker-state/local/fox-hop-boundary-v2/`:

- `measurements.json`: ten genuine X/Y branches through match frame 361, metrics,
  parser reports, schedules and build/ISO/tool identities.
- `recorded-buttons.json`: independently parsed X/Y masks and actual hold lengths.
- `fresh-three-request.slp`: matches the restored three-request X branch's bytes
  from a separate fresh session.
- `official-analysis/result.json`: both real official runs pass nine fields
  across 122 player-frames each, with full rendered coverage of 240..300.
- `official-analysis/comparison.mkv`: 61 frames at 60 FPS, **short hop left,
  full hop right**, plus an explicit image/game-frame CSV mapping.

The initial probe stopped at frame 301 while the full hop was still in its
Landing action. It failed the required return-to-idle check; that attempt remains
in `fox-hop-boundary-v1/`. The final probe extends to 361. Timing, math, state
tolerances and timer thresholds are unchanged. Parser acceptance and playback
remain separate checks; these partial recordings have no manufactured Game End.

Docker Python checks pass **246 tests**, including 11 new measurement/coverage
tests. Synthetic fixtures test arithmetic and rejection of interrupted/incomplete
traces; they do not simulate Melee or create replay files. Ten actual ISO
recordings and two real official executions provide separate gameplay evidence.
Generated game material and artifacts remain ignored.
