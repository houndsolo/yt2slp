# V100 replay collection

The user added 3,298 replays to the V100 checkout's `recordings/examples/`, for
3,326 files including the original 28 curated fixtures. Files were inventoried
read-only and left in place. The tracked fixtures remain tracked; new bulk `.slp`
imports are ignored along with generated recordings, images, videos and weights.

`tools/slippi-parser/catalog-replays.cjs` hashes supported-size files and reads
settings with pinned `@slippi/slippi-js@9.1.3`. It emits only setup, content
identity, filename-date grouping and reserved split metadata. It does not export
controller values, later player states or account fields. It detects content
duplicates and carries existing split reservations by replay hash.

The completed catalog is at V100
`/home/prompter/yt2slp/.docker-state/local/replay-catalog-v2/`:

| Result | Files |
| --- | ---: |
| Settings-eligible human NTSC singles | 2,224 |
| Four-player files skipped | 1,030 |
| One-player files skipped | 21 |
| CPU/non-human cases skipped | 31 |
| Ice Climbers/follower cases skipped | 19 |
| Unsupported oversized input retained | 1 |
| Total | 3,326 |

There are 3,325 hashed distinct files and no content duplicates among them;
14,009,873,262 bytes were read. The remaining file,
`Game_20260109T221249.slp`, is 14,012,446,720 bytes and exceeds the catalog's
64 MiB per-file memory bound. Its `parse_error` row explains that it was left
untouched and unhashed. It was not diagnosed or deleted. The earlier v1 catalog
also retained this file after Node rejected its size.

**58 candidates are Fox/Falco on Battlefield**, across 34 filename dates,
including the original training and now-examined validation matches. These are
settings candidates, not 58 audited renders or training-ready matches. Other
rosters/stages, mirrors, followers, doubles and CPU games remain outside the
current image model's narrow contract. Filename dates are grouping heuristics,
not verified sessions; player-disjointness is unestablished.

Rebuild into a new ignored output directory:

```bash
cd /home/prompter/yt2slp
bash scripts/docker.sh run node tools/slippi-parser/catalog-replays.cjs \
  recordings/examples .local/NEW-catalog configs/learning-pilot-split-v1.json
```

The [expanded frozen split](../configs/learning-corpus-split-v1.json) now assigns
34 training, 14 validation and ten test candidates while preserving the pilot's
date reservations. A completed six-train/two-validation starter selection has
4,448 images and 4,208 temporal windows. Server-local preparation and resumable
training controls are installed; see [training-control.md](training-control.md).
Test matches remain unrendered/unlabelled. Useful recognition remains unestablished.

Data expansion workflow:

1. Retain frozen train/validation/test membership by replay hash and whole date groups.
   Retain June 22 as training and June 23 as examined validation; reserve new
   dates for unseen testing before reading their control labels.
2. Render short compatible samples with official Playback and audit frame mapping,
   startup/configuration and phase evidence. Record failures instead of assuming
   every settings-eligible replay plays or aligns correctly.
3. Export supervised labels only into the appropriate training/evaluation side,
   use bounded decoded windows/cached features, and load windows by index.
   The new runner memory maps feature shards and materializes minibatches. The
   original smoke script's eager window stack remains confined to that small pilot.
4. Train across multiple matches, then evaluate frozen predictions on separate
   matches with event-sensitive metrics and neutral baselines. Preserve an unseen
   test group while iterating on development validation.

No extra hardware or manual per-frame controller annotations are needed to begin
this bounded expansion. Rendering/storage throughput and larger-run memory still
need measurement; the collection does not establish useful recognition by itself.
