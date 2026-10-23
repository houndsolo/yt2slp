# Consecutive reconstruction windows

The controlled workflow can select a short input program, carry its verified
controller history into a new native session, and search the next window. A fifth
reference case covers a short hop followed by a full hop over 161 video frames.
The joined genuine replay passes independent parsing, actual official Playback,
and a separate post-selection known-source comparison. Supplied starting
conditions and manual observations are still required.

## Continuing selected history

The engine retains one process checkpoint per session. `scripts/trajectory.py
seal` records selected segments, start recipe, source identity, native build/ISO/
boot hashes, last observation and genuine replay SHA-256 after fresh-run, parser
and official review checks. Exact image-score ties remain in the evidence;
the first declared minimum is carried forward.

`scripts/reconstruct_manual.py --prefix PREFIX.json` boots the same match and
reproduces the neutral opening and selected segments. Before capturing a new
session-local checkpoint, it checks exact boundary observations and recording
bytes. Changed source/start/native identities, state or replay hashes fail.
Segments share a boundary observation without repeating a step or adding a neutral
step. Each segment defines its initial input and phases. Replay events come from
the game throughout; `.slp` files are never concatenated. Trial restores retain
the engine's recording rewind behavior.

Completed selections can continue across sessions. Unfinished grids cannot resume;
automatic backtracking and exhaustive combinations of tied histories are absent.
Failures and completed prefixes remain available for inspection and reruns.

`scripts/window_video.py --video VIDEO --first 79 --last 160 --output NEW`
creates an inclusive contiguous decode-index view. It renumbers local indices and
adds `source_decode_index`, retaining the MP4 hash, original PTS, source-relative
seconds and image hashes. Relative PNG symlinks work across host/Docker mapping.
There is no re-encoding, interpolation, timestamp rebasing or game-frame inference.
Annotations bind to the particular view manifest.

## Host workflow

`scripts/reconstruct_windows.py` connects search, complete accepted-population
export, official rendering, ranking, fresh selection checks, review and sealing
for 2..32 consecutive annotated windows. It finally reproduces the joined history
in two fresh boots, parses it, captures official Playback and produces comparison
and verification reports.

A plan supplies full `video`, `timeline`, `render_interval`, and a `windows` list
with each window's `spec`, `video`, `timeline`, `regions` and optional
`manual_timers`, using existing manual schemas. Plan paths use Docker workspace
names: `.local/...` maps to host `.docker-state/local/...`; config paths are
repository relative. ISO/Dolphin arguments are host paths. Build/setup and the
pinned parser must already be installed. The validated local invocation was:

```bash
xvfb-run -a python scripts/reconstruct_windows.py \
  --plan .docker-state/local/manual-case-v5/plan.json \
  --output .local/joined-jumps-v1 \
  --iso /home/houndsolo/Documents/vanilla.iso \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --calibration .local/manual-case-v5/timer-calibration.json \
  --initial-search .local/runs/step-m2qthb1a \
  --reference-state .local/runs/step-j0x10eav/analysis-expanded-clock/native-state.json
```

Use a new output directory. Optional `--initial-search` requires a matching first
coarse-search specification. Optional `--reference-state` reaches only final
verification, after every selection; omit it for ordinary footage. Search/ranking
never read source player states or original controls. Commands/logs and completed
window metadata are retained. A fresh selection can reuse its actual candidate
capture only after replay bytes match exactly; joined playback gets a new capture.
This starts from ingested footage and annotations. Automatic cropping/observations,
unknown-start recovery and general visual acceptance remain separate work.

## Fifth controlled evaluation

`fox-falco-battlefield-two-jumps-v1` records 480 requests, holding X on zero-based
requests 244..245 and 324..327. Its reference covers game frames 240..400: 161
lossless images at 60 FPS. Fox/Falco, Battlefield, seed 1 and time-base 0 are supplied.

The old clock calibration lacked main-clock digits 3 and 4. Initial source analysis
failed timer coverage despite exact native/official fields. Before candidate
search, manually read source images `01:54.98` and `01:53.93` extended coverage.
Thresholds/scoring stayed unchanged. Five ambiguous compressed-video timer labels
were individually read; automatic failures and corrections remain retained.
Source-only cues/regions, grids and code identities were frozen before search.
Each grid has 24 X/Y programs: onset 2/6/10, hold 1/2/3/4 requests.

| Window | Simulation boundary | Rendered frames | Coarse accepted | Selected program | Exact image-score ties |
| --- | --- | --- | --- | --- | --- |
| First | 239 to 319 | 240..318 (79) | 8 of 24 | X onset 6, release 7: short hop | 8, 9, 10, 11 |
| Second | 319 to 401 | 319..400 (82) | 16 of 24 | X onset 6, release 9: full hop | 12, 13, 14, 15 |

All 24 accepted candidates were genuinely recorded, independently parsed and
actually rendered; their nine native/official fields agree. The second search
reproduced the first selected boundary and recording before branching. The joined
recording ends at 401 without invented Game End, SHA-256
`fe922b729470cc58e3977ba5a91a2259a7a5ac5d26b8ca01c22b555ccf04ae69`.
Two fresh boots reproduce joined observations/bytes. Official Playback with resync
disabled passes progression and nine-field checks across 322 player-frames.
After selection, all nine known-source fields also match across those player-frames.
All 54 known cues fit; 24 cues remain unknown. Whole-frame RGB RMSE is 5.47/255
over 161 frames, including compression, camera, HUD and background. No absolute
visual acceptance threshold, unique original controls, complete-state equality
or retail parity is established.

Ignored local evidence:

- Source and failed/final analyses: `.docker-state/local/runs/step-j0x10eav/`.
- Video/views/annotations/calibration/frozen protocol/plan: `.docker-state/local/manual-case-v5/`.
- Coarse searches: `.docker-state/local/runs/step-m2qthb1a/` and `step-typtf91s/`.
- Workflow, prefixes and all candidate captures/rankings: `.docker-state/local/joined-jumps-v1/`.
- Joined replay/parser/fresh checks/capture/verification: `joined/` under that
  workflow; side-by-side video: `joined/review/comparison.mkv`.
- `runner-used.py` retains the executed host runner matching `result.json`'s hash;
  the committed runner removes an unused loop only.

Docker's Python suite passed 275 tests, including identity/state/hash rejection,
input continuity and real FFmpeg window tests. Six host-workflow tests passed
again after cleanup. Engine/parser code is unchanged; its previous full suites
passed 10 host, 23 game-library and 9 parser tests. ISO/parser/GUI runs above are
separate evidence. Five sources sharing supplied fixtures do not establish
general reconstruction from tournament video.
