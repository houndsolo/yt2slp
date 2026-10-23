# First tournament-video intake

The user supplied [Ginger versus n0ne at Riptide](https://www.youtube.com/watch?v=OWraeXAYElQ).
The first twelve seconds were downloaded and inspected locally. This is footage
intake, not a reconstructed replay or a successful held-out reconstruction result.

## Observations

The selected public video-only stream, format 299, is H.264, 1920×1080 at 60 FPS.
`yt-dlp 2026.08.19` requested 0..12 seconds; the resulting MP4 has 721 decoded
frames, PTS 0..184320 at time base 1/15360. SHA-256:
`635289c32b6c21d9b9b19ddb9933bee933cb257177565d5068b78a71b3963f80`.
The endpoint includes the image at 12 seconds. Download-section boundaries are
not game-frame boundaries.

Manual inspection shows Falco versus Captain Falcon on Yoshi's Story, labels
P2/P3, four stocks each, damage 0/0 and initial clock `08:00.00`. Character/stage
screens, Ready and opening gameplay are visible. Explicit crop
`(612, 0, 1308, 1080)` excludes the stream sidebar and keeps gameplay. It is
manually reviewed; no resize or camera fit has been applied.

The ingested view selects source decode indices 330..600: 271 images at source
times 5.5..10 seconds. Every PTS delta is 256 (1/60 second). Identical adjacent
PNGs at indices 362/364 during Ready are retained. Regular video PTS do not
establish complete game-frame coverage.

Individual original-resolution clock readings:

| Source decode index | Source time | Observed timer |
| --- | --- | --- |
| 504 | 8.4 s | 08:00.00 |
| 505 | 505/60 s | 07:59.99 |
| 506 | 506/60 s | 07:59.98 |
| 507 | 8.45 s | 07:59.96 |
| 508 | 508/60 s | 07:59.94 |
| 509 | 509/60 s | 07:59.93 |
| 510 | 8.5 s | 07:59.91 |

These are observations, not native frame labels. The pinned game's countdown
centiseconds are `99 - trunc(99 * subsecond_tick / 59)`, in `gm_8016AF0C` in
`gm/gmvs.c`. They are not ordinary decimal timestamps at 60 Hz. The observed
sequence is compatible with that expression. Native/render phase and the exact
game-counter offset remain unverified.

## Reproduction

No credentials or browser cookies were used. Quote the output template under zsh:

```bash
yt-dlp --ignore-config --no-playlist --no-overwrites --no-part \
  --download-sections '*0-12' -f 299 \
  -o '.docker-state/local/youtube-OWraeXAYElQ/opening.%(ext)s' \
  'https://www.youtube.com/watch?v=OWraeXAYElQ'
bash scripts/docker.sh run python scripts/ingest_video.py \
  .local/youtube-OWraeXAYElQ/opening.mp4 \
  --first 330 --last 600 --crop 612 0 1308 1080 \
  --output .local/youtube-OWraeXAYElQ/gameplay-opening
```

Use new output directories. Inclusive `--first`/`--last` must be supplied together;
`--max-frames` bounds selected frames. Source probing allows at most 18,000 frames,
so trim long media first. RGB conversion before cropping prevents odd coordinates
rounding to a chroma grid. No interpolation/resampling occurs. The manifest retains
original source identity, PTS/source-relative times, decode indices, original
geometry, explicit crop and image hashes, leaving game alignment unknown. Default
ingestion remains unchanged. Tests compare actual cropped pixels and timestamps,
including a real variable-rate source with a missing video frame.

Ignored artifacts live in `.docker-state/local/youtube-OWraeXAYElQ/`: source,
metadata/download logs, timer sheets, `intake.json` and `gameplay-opening/`.
Each manual reading is bound to its image hash, PTS and original frame. No footage,
images, glyphs or generated annotations are committed.

## Reconstruction gaps

Current search assumes Fox/Falco on Battlefield, controlling one player while
the other stays neutral. The [native setup probe](tournament-start.md) now validates
Yoshi's Story, Falco/Captain Falcon on P2/P3 and explicit four-stock/eight-minute
rules with genuine recording and official Playback. Search still needs those
settings threaded through it, pre-clock control and simultaneous player programs.
Source/candidate geometry also differs; a future comparison transform must be
explicit and validated.

RNG, boot time base, exact controls, game revision/codes and world coordinates
remain unknown. Seeing the opening removes the need to invent a mid-match
history; it does not reveal hidden values. Next work is validating an appropriate
native start, then a short two-player continuation from source-only evidence.
No original `.slp` has been obtained or used as a reconstruction input.
