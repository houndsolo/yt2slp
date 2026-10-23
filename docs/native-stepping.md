# Native fixed matches and VI stepping

`NativeLinuxBackend.start()` boots a fresh process with a fixed match and a menu
script, then pauses at the first snapshot with VS major/minor scene `2/2`, a
positive match-frame counter, and exactly the configured two occupied slots. The match
countdown may still be running. `step()` resumes that same process to its next
VI retrace. `observe()` requests the paused snapshot without advancing anything.
Always use the context manager or call `close()` to release the child process.

```python
from pathlib import Path
from yt2slp.backend import NativeLinuxBackend, RunConfig
from yt2slp.match import MatchConfig, PlayerConfig, PadInput, NEUTRAL_PADS

with NativeLinuxBackend() as backend:
    backend.initialize(RunConfig(
        Path("build/headless/melee_headless"), Path("build/game/melee_game.so"),
        Path("/assets/melee.iso"), Path(".local/runs"),
        rng_seed=1, time_base=0,
        match=MatchConfig(stage=31, players=(PlayerConfig(2), PlayerConfig(20))),
    ))
    state = backend.start(Path("third_party/melee-unlocked/port/scripts/native_vs.txt"), timeout=180)
    for _ in range(240):
        state = backend.step(NEUTRAL_PADS)
    state = backend.step((PadInput(stick_x=80), *NEUTRAL_PADS[1:]))
    assert backend.observe() == state
```

Match settings use **external** `CharacterKind` and `StKind`, not the internal
fighter/stage IDs: Captain Falcon=0, Fox=2, Falco=20, Yoshi's Story=8,
Battlefield=31, Final Destination=32.
The initial supported configuration is two players, retail characters 0..25,
costumes 0..3, human/CPU selection and CPU levels 1..9. Other slots are empty.
Python and native CLI both reject values outside this scope. The existing game
hook applies the override at character preload and VS setup. `ports=(0, 1)`
selects physical P1/P2 by default; two distinct zero-based ports can be supplied.
Optional `StockRules(seconds=480, stocks=4)` selects stock mode and an explicit
countdown (whole minutes, 60..600 seconds; 1..4 stocks). Other rules retain fresh
menu defaults. Host API 19 appends that optional setup callback; rebuild host and
game together. Game structures, math flags, tick constants and physics are
unchanged. See [tournament setup](tournament-start.md) for the P2/P3 ISO probe. `requested_match` in experiment output is configuration, not a
measurement: the selected state snapshot does not contain stage/character IDs.

`RunConfig.match` also works with `run_script()`. Leaving it `None` preserves the
original batch runner's menu-selected match. Interactive `start()` requires it.

The unit of stepping is **one VI retrace**, not an assertion that one complete
match simulation frame elapsed. The callback runs after the host's existing
VI/alarm/audio work and before returning to the game. It blocks there, retaining
the live game stack; it never calls `game.run()` again or invokes `retrace()`
from Python. While paused, this thread cannot advance emulated ticks or service
callbacks. Control mode requires headless, unpaced operation. Wall-clock waiting
therefore does not make emulated time catch up on resume.

Each step supplies all four raw PADStatus samples. They replace scripted input
on all ports after bootstrap, and are used at the game's next ordinary PAD poll.
They do not rewrite already sampled input or promise zero input latency. Neutral
`NEUTRAL_PADS` connects physical P1/P2 and disconnects P3/P4. For custom
ports, use `match.neutral_pads()` and supply the desired active-port controls. CPU players retain the game's
AI behavior. Float observations preserve their original uint32 bits.

## Local ISO validation

From an updated checkout, using the existing Docker image:

```bash
git pull --ff-only
bash scripts/docker.sh setup
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run yt2slp step-experiment \
  --script third_party/melee-unlocked/port/scripts/native_vs.txt \
  --stage 31 --p1 2 --p2 20 --steps 600 \
  --seed 1 --time-base 0 --timeout 180 --repeat --check-input
```

Build the image with `bash scripts/docker.sh build` first if it is missing.
The command boots three independent processes: two with the same inputs and one
neutral control. It checks stable paused observations, exactly one retrace per
step, advancing match frames, equal selected fields across the repeated runs,
a matching neutral prefix, and different fighter fields after input changes.
A failed comparison exits 1.
This does not establish retail parity, every input's latency, full-state equality,
or checkpoint determinism. It does not need Dolphin.

Artifacts are in `.docker-state/local/runs/step-*` on the host: `config.json`,
`host.log`, full `state.csv` (including boot), and `inputs.txt` (input requested
after each recorded retrace). Control sessions use a fresh in-memory memory card. Batch runs use private
memory-card folders.
On errors, logs/partial traces remain but the Python observation history is
cleared. Boot has a retrace budget (default 6000) and each response has a finite
wall-clock timeout. Close/EOF stops the runner; a stuck process is killed/reaped.
Capture/restore now support one session-local Linux process checkpoint; see
[process checkpoints](process-checkpoints.md). Genuine selected-branch recording is now available; see [recording](slippi-recording.md).

## Protocol and test scope

A private inherited Unix socket carries ASCII protocol version `MUCONTROL 2`,
followed by `STATE ` and the existing 77-column state row. Stdout/stderr go to the
log and cannot masquerade as responses. Commands include `capture` and `restore`
(`CAPTURED`/`RESTORED` followed by the paused snapshot, or `UNSUPPORTED` without
advancing). The other commands are `observe`, `quit`, or
`step` plus 40 decimal integers: button, stick X/Y, substick X/Y, L/R triggers,
analog A/B, error for each of four ports. The native side validates all inputs
before applying any; malformed commands fail closed. Every accepted step returns
one snapshot at the next retrace. Version, field ranges, ordering, timeouts and
EOF are validated in Python as well.

Native tests use socket pairs and synthetic snapshots to exercise the actual
pause protocol, signed inputs, invalid/oversized/truncated commands, EOF and boot
limits. Python tests drive that same compiled protocol fixture and deliberately
broken peers to test lifecycle, cleanup and error reporting. These tests do not
simulate Melee or establish gameplay correctness. Real ISO validation remains a
local check; no retail ISO is available in the cloud workspace. The user has
reported passing the prior 600-step ISO experiment locally (match frames 1..601,
stable pauses, repeated-run agreement, matching neutral prefix and input effects).


`recording_status()` reads the selected branch's last recorded frame and genuine
Game End flag without advancing. Protocol command `record-status` returns
`RECORDING <signed-frame> <0|1>` or `UNSUPPORTED`. Complete timed-match recording
and restoration after completion are now validated locally; see
[recording and playback](slippi-recording.md).
