# First tournament opening: two-player search

Validated locally on 2026-10-23 using the user's ISO and the supplied
[tournament video](https://www.youtube.com/watch?v=OWraeXAYElQ). This is an
iterative development case with manual observations, not a blind evaluation or
a claim that the match has been reconstructed.

## What changed after reassessing the next steps

The opening needs controls before the countdown clock starts. It also needs
both physical controllers and the visible starting platforms. The immediate
sequence is now:

1. Observe the start, retain unknown settings, and control signed playable frames.
2. Search both players from a checkpoint with an explicit match recipe.
3. Reject wrong setup hypotheses; retain failures and alternative programs.
4. Export genuine selected-branch events, independently parse, reproduce from a
   fresh boot, and compare actual official Playback with the native recording.
5. Map source images explicitly, compare all cue-compatible candidates, and
   review motion error before expanding the grid or automating recognition.
6. Extend the reconstructed history into another window and another real clip.

A vision model is not required for this manual experiment. Recognition work
should follow measured gaps, rather than replace the simulation/playback checks.

## Observations and setup hypotheses

The source is cropped at `(612, 0, 1308, 1080)` to remove the stream sidebar.
Original MP4 PTS and source decode indices are retained. Source frames
505/510/515/520 show Falco at 0%, Captain Falcon at 3%, and Falco to the left.
Those are 16 known categorical cues. Facing and action groups remain unknown
(16 cues); no positions or original inputs are read from a source replay.
There is no source replay available.

Literal clock readings suggest replay frames 1/6/11/16, with each cue allowing
the declared alternatives one frame either side. All cues in one image must fit
the same alternative. This uncertainty is distinct from the exact timer labels
used for rendered-image comparison. The first clock decrement is not the first
playable frame: the source already contains movement and damage then.

The requested match is Yoshi's Story, Falco/Captain, physical P2/P3, four stocks,
480 seconds. Costumes 0, simulation RNG seed 1 and time base 0 remain explicit
hypotheses. Source RNG, game codes, boot history and hidden state are unknown.
The neutral Ready prefix is also a supplied hypothesis.

The first search used ordinary per-slot starts and rejected **all 72** programs.
Several matched damage, but the horizontal order was wrong. The source audit
found that default starts follow occupied player slots, not RNG. The Ready image
at source decode 400 visibly puts P2 on the left and P3 on the right.

`MatchConfig.spawn_points=(0, 1)` now exposes ordinary stage-defined start-point
indices in logical player order. Host API 20 appends optional fields to
`MuMatchOverride`; host and game must be rebuilt together. The game consumes
`StartMeleeData.spawn_pos` before ordinary match construction. This does not
identify the source's spawn codes or rewrite live coordinates, physics or math.
Omitting the option preserves existing behavior and replay bytes.

## Search and native/official validation

The second search changes only that initial-layout hypothesis; the 72 programs,
cue document, seed and time base are unchanged. The grid combines:

- Falco X at request 0/2/4, held two requests, then B at 8/12/16 for one request.
- Captain left stick -80, X at 0/4 held two/four requests, then stick release at
  16/24. Complete pad samples specify releases explicitly.

Checkpoint replay frame -40 precedes first playable frame -39. Each trial runs
58 VI requests to replay frame 18. Raw native observations keep their actual
match counter, including zero during Ready; signed keys are separately queried
from genuine recording status. The search refuses gaps or clock/port mismatches.
Restoring discards trial events; a rejected grid exports no `.slp`.

**24 of 72** programs pass the sparse cues:
`4, 5, 8, 10, 12, 13, 16, 18, 20, 21, 28, 29, 36, 37, 40, 42, 44, 45, 60, 61, 64, 66, 68, 69`.
The first declared accepted program, index 4, is a coarse selection, not a visual
winner. It uses Falco X at 0, release 2, B at 8, release 9; Captain left at 0,
X at 4, release X at 6, release stick at 16.

The selected genuine partial `.slp` reproduces raw observations, signed keys and
encoded bytes from a fresh boot. Pinned slippi-js parsing passes, with requested
settings and no fabricated Game End. Selected SHA-256:
`50ebfe94a30d5247ce38cfa414a1da08a77d89e5853226abaf2ce40fd4ab5b5e`.

Actual official Playback 3.5.2 with resync disabled progresses through the
requested opening and regenerates events. Across **-39..18**, all nine checked
fields match exactly for **116 player-frames**. Seven native observation fields
also match their recorded keys. These checks establish consistency of this
branch with its own playback; they do not compare hidden state with the video.
The separate strict Ready audit's one-word mismatch at -113 remains unresolved;
this playable-interval check does not supersede it.

The earlier default two-jump recording still has SHA-256
`ad32372acfbd9bb7df60a64d25e733e4a81bfb6fe14d877573672f52a3b3c98a`
after the API 20 extension.

## Image comparison and retained failures

All 24 accepted branches are exported and independently parsed. Source frames
505..521 form a 17-image comparison window. A fixed Lanczos transform maps the
1308x1080 gameplay crop to 642x528, preserving source timestamps and image
lineage. This slight anisotropic scale is declared, not fitted to candidates.
Six source-only fighter/platform regions at local frames 0 and 10 are frozen
before inspecting candidate poses. The existing equal-region, unshifted RGB MSE
objective and separate translation diagnostic remain unchanged.

The compressed source HUD fails automatic coverage. All 17 clock readings are
individually observed and identity-bound; automatic failures remain retained.
Clean official HUD templates come from earlier independent official probes.
Both calibrations retain the original recognition thresholds. The source-only
glyph templates are not assumed to recognize clean official images.
The initial clean-official calibration also fails complete timer coverage, even
after full Ready rendering produces gameplay images. That failure is retained;
no rendered winner or aligned comparison is accepted yet. Timer segmentation or
individually observed official labels must be validated before continuing ranking.

The initial request beginning at replay frame 0 passed progression and event
checks, but yielded only "Waiting for game" images. Image coverage rejected the
population and published no visual winner. Captures are retained. The capture
tool now permits an explicit earlier request start while keeping the wanted
comparison interval 1..17. Starting at -40 also retained the waiting screen;
starting at the first recorded frame, -123, produces actual gameplay images.
Timer coverage remains a separate gate. Progression, usable images and likeness
are separate.

## Commands and local evidence

The committed [grid](../configs/tournament-opening-v1.json) is source configuration.
Source annotations, video, images, parser exports, trial state and generated
recordings remain ignored local artifacts. Run native operations in Docker:

```bash
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/reconstruct_opening.py \
  --video .local/youtube-OWraeXAYElQ/gameplay-opening \
  --timeline .local/tournament-opening-v2/timeline.json \
  --spec configs/tournament-opening-v1.json
```

Use the resulting run path, rather than assuming a fixed temporary run name.
Actual official capture runs on the host:

```bash
xvfb-run -a python scripts/capture_benchmark.py \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso "$YT2SLP_ISO" --replay PATH_TO_RUN/selected.slp \
  --output PATH_TO_RUN/official --first -39 --last 18 --padding 0 \
  --include-preroll --request-start -123
bash scripts/docker.sh run python scripts/verify_opening.py --run DOCKER_RUN_PATH
```

Local artifacts:

| Evidence | Ignored host path |
| --- | --- |
| Failed ordinary-spawn grid, frozen code/protocol | `.docker-state/local/tournament-opening-v1/`, native `runs/step-ru10z2mp/` |
| Explicit-layout protocol, raw cues and all results | `.docker-state/local/tournament-opening-v2/` |
| Selected search, parser, fresh recording and official audit | `.docker-state/local/runs/step-ozreb1l0/` |
| Default byte regression | `tournament-opening-v2/legacy-regression.json`, native `runs/step-bgv4qfkk/` |
| Unusable zero-start captures and rejected rankings | `tournament-opening-v2/candidates/`, `ranking/`, `ranking-manual/`, `ranking-official-hud/` |
| Retained failed -40-start population | `tournament-opening-v2/candidates-preroll/` |
| Full Ready population | `tournament-opening-v2/candidates-ready/` |

Paths in the last two rows are under `.docker-state/local/`. Source MP4 SHA-256:
`635289c32b6c21d9b9b19ddb9933bee933cb257177565d5068b78a71b3963f80`.
Frozen protocols bind image, code and recipe hashes; failed hypotheses are kept.
No whole-match reconstruction, original-input recovery, source RNG recovery,
full-state equality or absolute visual acceptance is established.

The current Docker build passes 10 host/component and 23 game-library tests.
The Python suite passes 340 tests, including signed/raw counter separation,
independent controller release, failed-grid cleanup, explicit setup gates and
fixed spatial views with preserved nonzero PTS. The unchanged pinned parser's
last component run passed nine tests. ISO and official-image evidence is separate
from synthetic component tests.
