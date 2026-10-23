# Tournament match setup probe

The native backend can now request the visible stage, characters, ports and
stock/countdown settings from the [supplied footage](tournament-video-intake.md).
This validates configuration and controls, not reconstruction of that footage.

```python
from yt2slp.match import MatchConfig, PlayerConfig, StockRules

match = MatchConfig(
    8, (PlayerConfig(20), PlayerConfig(0)),
    ports=(1, 2), stock_rules=StockRules(seconds=480, stocks=4),
)
# Pass match to RunConfig. Supply all four physical ports for each VI step:
pads = match.neutral_pads()  # disconnected, neutral, neutral, disconnected
```

Characters/stages use external IDs; ports are zero-based. Unused player slots
are empty. Costume 0, seed 1 and time-base 0 are declared probe choices, not
recovered hidden values. Other rules, including items and teams, retain defaults.
`StockRules` supports 1..4 stocks and whole-minute countdowns from 60..600 seconds.
The default `MatchConfig()` and its native match argument remain unchanged.
The stepping/checkpoint CLI also accepts stage 8. Custom ports/rules currently
use the Python API or explicit native host arguments.

Both native host and game must be rebuilt: host API 19 appends an optional
stock-rule callback. The ordinary match constructor consumes the explicit rules;
game timing, speed, math, state structures and control wire format are unchanged.
The control/checkpoint gate and Python start check use actual occupied ports.
Scalar comparison accepts explicit `player_indices=(1, 2)` and preserves those
physical indices rather than relabelling them 0/1.

## Reproduction and evidence

```bash
bash scripts/docker.sh setup
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/probe_tournament_start.py record \
  --output .local/tournament-start-v1
xvfb-run -a python scripts/capture_benchmark.py \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso "$YT2SLP_ISO" \
  --replay .docker-state/local/tournament-start-v1/selected.slp \
  --output .docker-state/local/tournament-start-v1/official \
  --first 1 --last 421 --padding 0
bash scripts/docker.sh run python scripts/probe_tournament_start.py verify \
  --run .local/tournament-start-v1
```

Use new output directories. Recording happens in Docker, official GUI playback
on the Arch host. The probe warms up to game frame 241, captures once, then runs
180-request continuations to 421. Test inputs jump Falco on P2 and move Captain
Falcon on P3; these are not inferred source inputs. All three restores pass,
both fighters respond, matching continuations/fresh observations agree, and
original/repeated/selected/fresh recordings have the same hash:
`1d4ad2fa0b2e37b48ba5f091575a57755f46ac27498b3e9a44cb20b0f8d0c26c`.
The neutral branch has a different hash. The unfinished match has no Game End.

Independent parsing confirms stage 8, Falco/Captain Falcon on P2/P3, four stocks
and 480 seconds. Parsed `inGameMode` is 32, the stock-mode bitfield. Actual
official Playback 3.5.2 with resync disabled passes progression and regenerates
matching nine-field events across all 842 player-frames, 1..421. The seven common
native observation fields also match those recorded events. Render/post-update
phase equality, complete state and source-video accuracy remain unmeasured.

Ignored evidence: `.docker-state/local/tournament-start-v1/`, native run
`.docker-state/local/runs/step-zpatxmzl/`, build logs
`.docker-state/local/tournament-start-build-2.log`. The initial build check found
two synthetic fixtures claiming six active players; they now declare two players
so their intended malformed-checkpoint checks still run under the stricter gate.
Final suites pass 307 Python, 10 host/component and 23 game-library tests.
Parser implementation is unchanged; its last component run passed 9 tests.

A fresh default two-jump source at `.docker-state/local/runs/step-z6gbaa8k/`
matches the earlier source recording exactly, SHA-256
`ad32372acfbd9bb7df60a64d25e733e4a81bfb6fe14d877573672f52a3b3c98a`.
See `legacy-regression.json` in the probe directory. Previously sealed prefixes
remain bound to their exact native binaries; changed builds intentionally fail
prefix identity checks even when this default recording still reproduces.

## Remaining opening-control gap

The source already shows movement and damage before its clock first decrements.
Slippi's pinned parser declares `Frames.FIRST_PLAYABLE = -39`; frame 0 is not the
first playable moment. Current native control starts at a positive match counter.
The footage's first `.99` timer reading must therefore not be treated as an idle
opening or used to discard the earlier playable frames. The next step is control
and recording validation through that pre-clock interval, followed by source-only
action annotations and simultaneous two-player input search. Search/refinement
still has controlled Fox/Falco/Battlefield assumptions and fixed image geometry.
