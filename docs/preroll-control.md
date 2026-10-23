# Control before the clock starts

The supplied tournament video already shows movement and damage before its first
`07:59.99` clock reading. The pinned Slippi parser declares first playable frame
`-39`; the previous native control start waited until positive frame 1. Treating
the first clock decrement as an idle match start would discard relevant inputs.

The backend now supports an optional earlier pause:

```python
state = backend.start(boot_script, include_preroll=True)
# Measured in the Yoshi/P2/P3 probe:
assert state.match_frame == 0
assert backend.recording_status().last_frame == -123
```

This pauses at the first VS boundary with exactly the configured fighters. The
ordinary `start()` behavior is unchanged. Each `step()` still advances one VI.
During Ready the native match counter remains zero while the separately observed
signed replay counter advances. Read `recording_status()` to label those replay
frames; do not invent a signed match counter or infer it from image order.
`start-options.json` retains the chosen mode. The native flag is
`--control-preroll`, valid only with `--control-fd`.

Capture/restore is supported at this earlier boundary under the same one-checkpoint,
single-thread/session-local restrictions. Game ABI, math and timing are unchanged;
this change moves the host's pause gate. The earlier stock-rule callback remains
host API 19. Rebuild the headless host before using the new option.

## Genuine recording and official evidence

```bash
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/probe_preroll.py record \
  --output .local/preroll-probe-v1
xvfb-run -a python scripts/capture_benchmark.py \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso "$YT2SLP_ISO" \
  --replay .docker-state/local/preroll-probe-v1/selected.slp \
  --output .docker-state/local/preroll-probe-v1/official \
  --first -39 --last 140 --padding 0 --include-preroll
bash scripts/docker.sh run python scripts/probe_preroll.py verify \
  --run .local/preroll-probe-v1
```

The capture flag explicitly permits negative requests bounded by the recording's
first frame, -123. PNG indices remain unrelated to replay frame numbers until
independently aligned. Repeated `08:00.00` labels cannot uniquely label Ready images.

The local Yoshi's Story/Falco/Captain Falcon P2/P3 probe starts at signed replay
frame -123, captures at -40 (native match counter still 0), and runs 180-request
continuations to 140. Both players' chosen inputs change observed state before
frame 0. Three restores preserve the paused state and matching continuations;
the neutral branch differs. Original/repeated/selected/fresh recordings match:
`8d68fc03358944b443d0e41dd77b23a8788a0042968d3d41ac6a97289c440152`.
Independent parsing confirms contiguous -123..140 events and no Game End.

Actual official Playback 3.5.2, resync disabled, passes the requested -40..141
progression. The **predeclared playable interval -39..140 matches all nine fields
exactly across 360 player-frames**. Native observations match their own seven
recorded fields across all 528 player-frames from -123..140, using the signed
recording counter observed at each paused boundary.

The wider strict Ready audit **fails**: one Falco Y value at frame -113 differs by
one float32 word, native `1105221348` versus official `1105221347`
(28.04242706298828 versus 28.04242515563965). Every other compared word matches.
No tolerance, math change or frame offset has been introduced. Full-recording
`passed` remains false and `verify` exits 1; the exact requested-interval result
is a separate field. This is bounded playable-interval validation, not full
Ready-state equality, retail parity or reconstruction of the source video.

Ignored evidence: `.docker-state/local/preroll-probe-v1/`. The first failed full
audit is in `official-analysis/`. A supplemental audit retaining both scopes is
in `official-analysis-requested/`, generated with `verify --output` pointing at
that new directory. Both strict full audits still fail. `probe-used.py` retains
the exact record-stage script; the later verifier adds the requested-interval
report. The native run is `.docker-state/local/runs/step-8aj5oakg/`.

The default two-jump recording still reproduces byte-for-byte after this host
change, SHA-256 `ad32372acfbd9bb7df60a64d25e733e4a81bfb6fe14d877573672f52a3b3c98a`;
new run `.docker-state/local/runs/step-9nlj81um/`, with `legacy-regression.json`
in the probe directory. Docker passes 309 Python and 10 host tests. The unchanged
game/parser's previous suites passed 23 game-library and 9 parser tests. Synthetic
transport tests additionally cover zero-counter stepping/restoration and capture
request bounds; they are separate from real gameplay evidence.
