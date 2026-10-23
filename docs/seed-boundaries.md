# Explicit native seed boundaries

The native backend now distinguishes two initial RNG boundaries. A seed number
without its application point is insufficient to reproduce a supplied setup.

| Setting | Behavior |
| --- | --- |
| `item-setup` (default) | Preserve the existing override immediately before item initialization consumes randomness. It occurs after Game Start recording. |
| `slippi-game-start` (opt-in) | Supply the initial seed at the native equivalent of Slippi RestoreGameInfo, before recording Game Start and constructing the match. Disable the later item-setup override. |

Python configuration uses `RunConfig(..., rng_seed=33480,
rng_seed_boundary='slippi-game-start')`. The native CLI accepts
`--rng-seed 33480 --rng-seed-boundary slippi-game-start`; it rejects that boundary
without an explicit seed. Opening-search JSON uses the optional
`"rng_seed_boundary": "slippi-game-start"`. Omission preserves previous behavior.
Legacy multi-window prefix recipes continue to support `item-setup` only.

Host API **21** appends an optional Game Start seed callback. The host enables
exactly one of the two callbacks for a requested seed. The game checks version,
callback and presence before writing the real initial RNG. It applies the new
request only to offline VS setup, at the same location as the existing replay
RestoreGameInfo path. Actual replay playback and online setup retain their own
seed handling. Rebuild host and game together; game API 6, observation layout,
control protocol, physics/math flags and VI timing remain unchanged.

The ordinary game event writer records the resulting RNG in Game Start. No
replay header or event payload is edited afterward. Search and population export
require the independent parser's recorded seed to equal the declared seed in
this mode; image ranking checks that identity again.

The source implementation reference is Slippi's
[RestoreGameInfo](https://github.com/project-slippi/slippi-ssbm-asm/blob/ee0f9cbcd7d0442ef80eb85f942f8be234affd4d/Playback/Core/RestoreGameInfo.asm),
hooked at `0x8016e748`. This feature aligns that initial boundary, not all of a
source replay's codes, subsequent RNG state, controls or hidden state.

## Validation

The supplied Fox/Falco Battlefield example records Game Start seed 33480. With
the new option, the unchanged 64-program search records **33480**, logs one Game
Start application and zero item-setup resets, and retains accepted indices
40/48. Fresh raw observations, signed keys and genuine replay bytes reproduce.
The failed earlier boundary check remains in `example-reference-v1/`.
Both accepted branches parse and render in official Playback with resync off;
all nine selected fields match their native recordings over 1..17 (68 total
player-frames). The unchanged image objective selects 48 again. These are own
playback checks, not equality with the source trajectory.

The default two-jump benchmark still produces exactly
`ad32372acfbd9bb7df60a64d25e733e4a81bfb6fe14d877573672f52a3b3c98a`.
GCC 14 Docker checks pass **348 Python, 10 host/component and 23 game tests**.
They cover boundary parsing, callback exclusivity, old-version/null guards,
transport/configuration preservation and unchanged default behavior. The source
parser/preparation suite remains separately validated at 12 tests.

Ignored local evidence is under `.docker-state/local/example-reference-v2-seed/`:
`seed-check.json`, `default-regression.json`, `protocol.json`, `search.log`,
and `candidates/`. The native search run is `runs/step-__9qzj2u/`; the default
regression is `runs/step-osoiqcdo/`. Broader code-set/source-state equality and
visual accuracy remain separate gates.
