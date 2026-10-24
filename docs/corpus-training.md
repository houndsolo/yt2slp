# Expanded server-local Fox training run

The new `corpus-v3` pipeline runs completely on `prompter@10.12.0.10`.
The Ryzen 7 5700X has eight physical cores/16 threads, 32 GB system RAM and the
32 GB V100. At setup, about 668 GiB disk was free. Footage, audits, feature
encoding, model training and controller reviews all run on this server. The
workstation and its SSH connection can be shut off after a worker launches.

## Data scope and frozen plan

A fresh settings-only catalog inspected all 3,326 files. The existing 64 MiB
per-replay bound still skips the anomalous 14 GB file without deleting it.
Sources must be human NTSC singles on **Battlefield**, with four stocks and an
eight-minute countdown. Matchups are **Fox–Fox or Fox–Falco**. Fox mirrors must
use different costumes. Unknown dates, short games, doubles, CPUs, other
rosters/stages and ambiguous mirrors are excluded. This retains one calibrated
stage while adding substantial match/motion diversity.

The versioned [split plan](../configs/learning-corpus-split-v3.json) contains:

| Split | Fox–Fox | Fox–Falco | Total |
| --- | ---: | ---: | ---: |
| Training | 36 | 34 | 70 |
| Development validation | 16 | 14 | 30 |
| Reserved final test | 12 | 10 | 22 |

Existing date-group and replay reservations are preserved. New sources on an
existing date inherit its split. Dates are filename heuristics; player
disjointness across dates remains unverified. Test sources receive no rendering,
feature encoding or controller/state-label export.

Each train/validation match gets three non-overlapping 1,200-frame clips, spread
across separate thirds of its available duration. Source hashes determine the
positions before labels or model scores are read. The first ten seconds and
last two seconds are excluded. The plan totals **300 clips / 360,000 frames /
100 minutes**, before failed captures/audits are excluded. All-success temporal
window totals would be 245,700 training and 105,300 validation windows.

## Evidence and acceptance

Three isolated official Playback/Xvfb processes render in parallel. Each has
its own Dolphin user directory. Rendering uses the unchanged official 3.5.2
binary and local ISO, software Mesa with two threads per render, and a shared
memory allowance of 2 GiB. GPU feature encoding is bounded separately.

Every selected VI still requires exact independently decoded UI frame indices,
one completed clean PNG and the fixed audited one-swap association. Parallel
startup waits for the paused counter to settle; transport failures get at most
three retained capture attempts. No failed input/state audit is relaxed or
silently promoted by a retry.

The bulk pipeline declares a different HUD corroboration policy from the old
strict mode: at least **90%** of selected positive frames must have readable
timers, every readable timer must agree with its UI label, and no unreadable run
may exceed 120 frames. Unreadable HUDs stay explicitly unknown. Bright effects
can obscure timer OCR without making the separately verified UI frame unknown.
The original strict policy and literal visual-reading option remain available.
This corpus policy is fixed before the batch, not fitted per clip.

Nine original/official post fields must match exactly for the entire selected
interval, with resync disabled, no fitted offset and no floating-point tolerance.
Original physical buttons and press/release labels must be present. Labels come
from the original recordings, not regenerated Playback PAD fields. MP4 frame
count, geometry, 60 Hz timestamps and decoded-image hashes are verified.

The zero image/post convention is explicitly transferred from the audited
Fox–Falco reference through the same capture pipeline. **Independent phase review
for every target, including the Fox mirror roster, is not established.** The
dataset records this experimental transfer. Neither full-state/image equality,
native UCF parity nor useful learned recognition is claimed by preparation.

Failed clips retain logs/artifacts and stay out of features. The dataset is
published after the planned attempts finish, only if at least 20 training and
five validation matches pass and both rosters occur in both development splits.
`status` reports actual accepted/failed counts; 100 minutes is the planned
maximum, not a promise of that much accepted footage. A 100 GiB disk reserve
stops new captures before filling the server. Completed work survives retries.

## Player identity and training

The earlier model used semantic Fox/Falco slots and cannot represent two Foxes
under that contract. The new model uses **ascending occupied physical ports**
for its two output slots. Costumes and per-port character assignments are bound
to each clip; swapped ports and mirrors are validated explicitly. This ordering
uses supplied replay setup, not a label-optimized or image-fitted permutation.

The network remains the frozen pretrained ResNet18 spatial encoder plus the
917,364-parameter temporal proposal model. It predicts physical button holds/
edges, effective axes and auxiliary state from 31-frame image windows. Windows
never bridge separate clips or matches. The new reader supports several
memory-mapped shards from one replay without treating them as duplicate sources.
No controller/state target is a network input.

The new run starts fresh because output-slot semantics and data changed. Its
configuration uses batch size 64, up to 200,000 total updates, checkpoints every
1,000 and complete development validation every 5,000. Best mean button-event
F1 selects the saved best model; training loss alone does not establish quality.
The previous 100,000-step model, datasets, metrics and checkpoints are preserved.
Its original trainer/data/model files are unchanged so its contracts remain valid.

## Self-service commands

`~/train-melee` now selects
[`configs/vision-v100-corpus.json`](../configs/vision-v100-corpus.json) by default:

```bash
~/train-melee status
~/train-melee logs --preparation --follow
~/train-melee stop-preparing
~/train-melee prepare                 # resume completed work / retry failed clips
# Once preparation reports ready:
~/train-melee start
~/train-melee pause
~/train-melee resume
~/train-melee stop
~/train-melee logs --follow
~/train-melee review --best
```

Review pauses active training and renders a fixed balanced sample of up to four
validation clips. Image-only predictions are frozen before scoring labels are
read. These MP4/MKV files compare original footage with recorded/predicted
controls; they still contain no reconstructed gameplay. Test sources stay sealed.

The old run remains available explicitly:

```bash
~/train-melee status --config configs/vision-v100.json
~/train-melee review --best --config configs/vision-v100.json
```

Workers run detached with networking disabled and restart policy `no`. After a
server reboot, use `prepare` for interrupted footage work or `resume` for model
training. Preparation, training and review share one controlled GPU workload at
a time. A completed full dataset and its checkpoint contract are immutable:
expanding it after training starts requires a separate data/run directory.

Paths on the V100:

```text
.docker-state/local/replay-catalog-v3/           settings inventory
.docker-state/local/vision-corpus-v3/            selected clips, evidence, MP4s, features
.docker-state/local/vision-training/corpus-v3/   new model/checkpoints/metrics/reviews
.docker-state/local/vision-training/default/     preserved old model
```

## Setup validation and current handover

The full 300-clip preparation worker has been launched detached on the V100.
It reuses four audited feature shards and continues with the remaining clips.
The complete production dataset is not yet published and production training
has not started. Use `status` and preparation logs; start training after `ready`.

Actual setup checks passed:

- Four 20-second clips cover both rosters and both development splits: 4,800
  exact UI/PNG labels, all 4,800 HUD timers readable and agreeing, nine exact
  original/official fields across 9,600 player-frames, and original controls/GPU
  features. The first parallel startup failure is retained separately in
  `vision-corpus-v3-pilot/`; the final validation has four accepted/zero failed.
- An isolated CUDA smoke run starts detached, pauses at step 40, resumes and
  stops at 60. Its two validation controller-review MP4s complete with exit zero
  under `vision-training/corpus-v3-smoke/reviews/`. These 60 updates are lifecycle
  evidence, not recognition acceptance or production training.
- The previous 100k model's pointer and payload checksum remain valid.
- Docker checks pass 435 core Python tests, 11 legacy/corpus trainer tests, eight
  model tests and 17 parser/preparation/export/catalog tests. CPU resumed versus
  uninterrupted optimizer/model/RNG equality passes; cross-hardware CUDA bitwise
  equality is not claimed.

Game assets, all imported replays, footage, labels, model weights and generated
artifacts remain ignored by Git. Dataset readiness and actual running worker
state are reported by `~/train-melee status`.
