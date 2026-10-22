# Native recording and official Playback Dolphin

## Installed playback executable

On this Arch host the official launcher has installed separate editions:

- Playback: `/home/houndsolo/.config/Slippi Launcher/playback/Slippi_Playback-x86_64.AppImage`
- Netplay: `/home/houndsolo/.config/Slippi Launcher/netplay/Slippi_Online-x86_64.AppImage`
- Launcher: `/home/houndsolo/Documents/Slippi-Launcher-2.15.2-x86_64.AppImage`

The launcher itself is not `YT2SLP_DOLPHIN`. Targeted inspection of its Settings
found the supplied ISO path. No authentication data or unrelated configuration
was dumped. Playback is present; installation through the launcher is unnecessary.
The Playback executable reports **3.5.2**, independently of launcher version 2.15.2.
Its installed AppImage SHA-256 is
`b26527c782e640ca52886d16d3886b9d0741a17d7ceb5addd2a6974e9ed66d54`.
This identifies the tested installation, not a signature-verification claim.

Host configuration (also saved locally in ignored `.local/playback.env`):

```bash
export YT2SLP_DOLPHIN='/home/houndsolo/.config/Slippi Launcher/playback/Slippi_Playback-x86_64.AppImage'
export YT2SLP_ISO='/home/houndsolo/Documents/vanilla.iso'
```

The installed binary's `--help` confirms `--exec`, `--slippi-input`, `--user`,
`--batch` and `--cout`. `--slippi-input` takes a **JSON request**, not a replay
file. Its schema was checked against the
[official communication specification](https://github.com/project-slippi/slippi-wiki/blob/master/COMM_SPEC.md).
The minimal request is `{"replay":"/absolute/path/game.slp"}`. Our harness also
sets `mode`, `commandId`, `startFrame`, `endFrame` and `shouldResync: false`.
Do not reuse assumed flags from unrelated Dolphin versions.

This session's sandbox cannot mount the AppImage using FUSE. For verification,
the installed image was extracted, without modification, under ignored
`.local/playback-inspect/` using `--appimage-extract`. Its `AppRun` ran under
`xvfb-run` on the Arch host. A private `--user` directory prevents changes to
normal Playback/Netplay profiles. No user GUI action was necessary.

Use the original AppImage normally on a FUSE-enabled host. To reproduce extraction:

```bash
mkdir -p .local/playback-inspect
(cd .local/playback-inspect && "$YT2SLP_DOLPHIN" --appimage-extract)
xvfb-run -a .local/playback-inspect/squashfs-root/AppRun --help
xvfb-run -a .local/playback-inspect/squashfs-root/AppRun --version
```

Run GUI playback on the host. Docker sees the ISO as `/assets/melee.iso`, native
builds as `/work/build`, and recordings as `/work/.local/runs/...`; those are not
host playback paths. On the host, recordings are `.docker-state/local/runs/...`.
`scripts/docker.sh` deliberately does not forward the host Dolphin path or display.
A missing Dolphin inside Docker is expected and does not invalidate native runs.

## Recording contract

`NativeLinuxBackend.start()` enables the game's existing native recording hooks
for the vanilla control session. `record(path)` exports the currently selected
branch's complete event prefix, including events before checkpoint capture.
It does not resume the game, restart simulation, or synthesize observations as
replay events. Batch `run_script()` recording is not implemented; export requires
a live control session. Non-vanilla recording, mods and online transport are
outside this adapter's scope.

The host forwards game-generated Game Start, frame, item, stage and Game End
payloads to the existing `NativeReplayStream`. Vanilla recordings use the same
Gecko terminator as the full host's vanilla recorder. The existing encoder adds
the declared event-size table, message-splitter Gecko event and UBJSON metadata.
Metadata timestamps derive from the configured console boot time. With time-base
zero they are in 2000, intentionally deterministic. The upstream encoder's
`playedOn: dolphin` compatibility metadata does not mean native simulation ran
inside Dolphin.

The stream stays in private process memory with no spectator sink or append-only
replay output. Linux process capture preserves it; restore discards the branch's
events and character-usage metadata together with the game/host state. No separate
stream rewind or shared file offset is involved. Explicit exports are immutable
artifacts of the branch at the time requested; restoring later does not retract
those files. The destination must not exist. Publication uses a temporary sibling
and an exclusive atomic hard link; transport/write failures do not publish a
partial destination. The destination filesystem must support hard links.

The private version-2 protocol adds `record`: `REPLAY <byte-count>`, bounded hex
chunks and `RECORDED`, or an explicit `UNSUPPORTED` reply. No snapshot or game
frame is sent in place of replay data. Missing events, invalid payloads and
stream limits fail explicitly. The upstream stream caps events at 256 MiB.
One match per session is supported; a second Game Start fails rather than silently
replacing the recording. Start a new backend session for another match.

An export from a live unfinished game is a **partial recording**: there is no
Game End event unless the game actually emitted one. Export and close never
invent a winner, end method, placement, or final input. Parser acceptance and
Playback frame progression do not turn it into a completed game.

## Reproduce validation

Use Docker for the native build, experiment and independent parser:

```bash
bash scripts/docker.sh build  # includes Node/npm for the independent parser
bash scripts/docker.sh setup
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run python scripts/record_checkpoint_experiment.py
bash scripts/docker.sh run npm ci --prefix tools/slippi-parser --ignore-scripts --no-audit --no-fund
# Substitute the run directory printed by the experiment:
bash scripts/docker.sh run node tools/slippi-parser/validate.cjs .local/runs/step-REPLACE/selected.slp
```

The experiment captures at match frame 241 and compares four 180-step
continuations ending at 421. Identical continuations must match both selected
observations and encoded replay bytes, including after the divergent branch.
The parser is independently pinned to `@slippi/slippi-js@9.1.3` with a lockfile.
It requires two-player settings, contiguous frames from -123, and pre/post events
for both players, and reports whether a real Game End exists.

For actual playback, use host paths and a new output directory:

```bash
xvfb-run -a python scripts/validate_playback.py \
  --dolphin .local/playback-inspect/squashfs-root/AppRun \
  --iso /home/houndsolo/Documents/vanilla.iso \
  --replay .docker-state/local/runs/step-REPLACE/selected.slp \
  --last-frame 421 --output .local/playback-NEW
```

On a desktop, omit `xvfb-run -a` and use `--dolphin "$YT2SLP_DOLPHIN"`.
The harness retains the request, private profile, stdout and result JSON. It
requires contiguous reported frames beginning at -123 and reaching the requested
last frame, then terminates its own Dolphin process group. This termination is
not evidence of Game End. `shouldResync` is false so replay resync is not being
used to mask divergence. No frame/state parity comparison is implemented.

## Measured results — 2026-10-22

- Docker GCC 14: 10 native host/component tests, 23 game-library tests and 96 Python
  tests pass. New tests cover recording chunks, malformed/oversized/truncated
  replies, non-advancing export, exclusive publication and cleanup on write failure.
  Synthetic transport tests are not gameplay or format evidence.
- Real ISO recording artifacts: `.docker-state/local/runs/step-qa9h0_nl/`.
  The original, identical and selected continuations encode identically at
  181,236 bytes; the neutral divergent branch differs. All three restores work.
- Independent parser report: `parser-result.json` in that run. Fox=2, Falco=20,
  Battlefield=31; 545 contiguous frames -123..421 with both players' pre/post
  events; Game End absent, as expected for this bounded recording.
- Official Playback 3.5.2: `.local/playback-full/result.json` and `stdout.log`.
  With that selected replay and the user's ISO, contiguous reports cover
  -123..422, reaching the entire recorded interval. Resync is disabled. The
  harness stops the process after success. Native recording and official playback
  were actually run locally; this is separate evidence from parser acceptance.

These results do not establish full-state equality, rendered-image agreement,
retail parity, complete-match ending behavior, mods, online play, or recording
across multiple matches. Physics, game math flags, ABI and console tick/retrace
constants were not changed.
