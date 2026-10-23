# Optional first vision/temporal experiment

The core engine environment has no ML dependency. Optional, separate CPU and
CUDA environments have been exercised inside the existing GCC 14 Docker image.
They do not replace host Python or alter game math. See the
[remote V100 setup](../../docs/remote-training.md) for the tested CUDA lock,
explicit device selection and actual GPU execution checks.

For the server-local multi-match runner and manual **start / pause / resume /
stop** controls, use `~/train-melee` on the V100. See the
[training control guide](../../docs/training-control.md). Its detached workers,
prepared feature shards and durable model/optimizer checkpoints work without
Codex or the workstation. The older commands below reproduce the bounded pilot;
`train_smoke.py` is not the long-running controller.

The executable experiment is a **training-clip optimizer smoke test**. It cannot
reconstruct a match, validate held-out accuracy or export a replay. Image/post
phase remains unverified in the original positive-clock pilot; that manifest
says `training_ready: false`. The [signed-frame follow-up](../../docs/signed-training-data.md)
now passes a bounded phase audit and training-clip overfit criteria on 241 frames.
Its pair manifest is ready within that scope. The native VI adapter and held-out
recognition remain unvalidated. Declining loss alone is not overfit acceptance.

## Reproduce the small pilot

First prepare an official supplied-replay video using the
[benchmark workflow](../../docs/example-replay-benchmark.md). Existing local
evidence uses `Game_20260622T203533.slp`, with the three-second prepared video
under `.local/example-reference-v1/video` **inside Docker**. On the host that is
`.docker-state/local/example-reference-v1/video`.

The following retains each run in a new ignored directory. Source controls are
intentionally training labels; they must never be passed to held-out inference.

```bash
bash scripts/docker.sh run uv venv --python python3.13 .local/learning-venv
bash scripts/docker.sh run uv pip sync \
  --python .local/learning-venv/bin/python tools/learning/requirements-cpu.lock \
  --index-url https://download.pytorch.org/whl/cpu

# Create the ignored output root first, inside Docker.
bash scripts/docker.sh run mkdir -p .local/learning-NEW
bash scripts/docker.sh run bash -c \
  'node tools/slippi-parser/export-training.cjs recordings/examples/Game_20260622T203533.slp -40 180 > .local/learning-NEW/labels.json'
bash scripts/docker.sh run python scripts/build_training_pairs.py \
  --video .local/example-reference-v1/video \
  --labels .local/learning-NEW/labels.json \
  --split-plan configs/learning-pilot-split-v1.json \
  --output .local/learning-NEW/pairs --context 31

bash scripts/docker.sh run .local/learning-venv/bin/python tools/learning/test_baseline.py
bash scripts/docker.sh run env TORCH_HOME=/work/.cache/torch \
  .local/learning-venv/bin/python tools/learning/train_smoke.py \
  --pairs .local/learning-NEW/pairs/pairs.json \
  --output .local/learning-NEW/smoke --steps 100
```

The encoder's first use downloads official torchvision ResNet18 weights into
the ignored cache. The report records their SHA-256. The CPU dependency lock
is separate from `uv.lock`; install it only in the optional environment. A
PyTorch cache override handles the Docker UID without a passwd entry. Its
original failed smoke log is retained locally.

## Architecture and supervision

A frozen [pretrained ResNet18](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.resnet18.html)
encodes each whole frame, padded to 384×320 without a central crop. Spatial 2×3
pooling produces 3072 features. A learned projection and bidirectional GRU with
128 hidden units read 31 consecutive 60 Hz frames, including future context.
The 917,364 trainable parameters predict the center frame for the two declared
physical-port slots. Changing match configuration is outside this narrow smoke
test; no automatic visual roster/player association exists. Frozen inference now
maps the known unique Fox/Falco character slots to supplied physical ports;
mirrors and doubles remain unsupported.

Heads predict 12 physical button holds, presses and releases; 17-bin categorical
effective values for four stick axes and the combined trigger; action ID; and
airborne state. Masks remove unavailable labels from every loss. Positive
button weighting uses only training labels; reported event F1 exposes missed
edges rather than rewarding neutral outputs. Axis heads allow alternatives
independently; joint sequence uncertainty, consistency constraints, native input
adaptation and simulation-guided proposals remain future work.

The [Slippi format](https://github.com/project-slippi/slippi-wiki/blob/master/SPEC.md)
distinguishes effective pre-frame controls, physical controls and post-frame
state. The pinned parser exposes raw main-stick X but **not** raw main-stick Y
or raw C-stick axes. The exporter masks those fields explicitly even when the
newer replay contains them; it does not reconstruct raw bytes from floats.
Exported JSON excludes player/account names and free-form metadata. The rendered
source images themselves retain the original replay's normal HUD/name display.

Whole-match/date grouping is frozen before windows. The examined June 22 match
is training; the June 23 Fox/Falco Battlefield match is reserved for validation.
This is not a player-disjoint split: player separation across dates is unknown.
The first run uses only the training clip, with no validation evaluation.

## Measured pilot and remaining gates

Local evidence: `.docker-state/local/learning-pilot-v1/` on the host.

- 180 positive-clock images, 360 player-frame targets and 150 overlapping windows.
- 100 CPU optimizer updates, seed 1: training loss **10.51475 → 1.83518**.
- Training F1: holds **0.374**, presses **0.048**, releases **0.043**. This is
  weak edge learning, not a solved training clip or generalization result.
- Latest Docker validation passes **403 Python tests** and **eight optional model
  tests**. The parser/preparation/export/catalog suite passes 17 tests.
  Models/features, frames and labels stay ignored. Native code is unchanged;
  native suites were not rerun here.

Falco's initial dash → short-hop laser → fast-fall occurs **before frame 0**:
the replay labels show dash at −31, X held −28..−26 and released −25, airborne
at −23, B at −16 and vertical speed −3.5 at −10. These labels are now intentionally
examined as a training case. The existing MP4 starts at frame 1, so this opening
is **absent** from its images/windows. Exporting those controller labels does
not itself supply correctly aligned pre-clock training images.

The signed-frame follow-up fills the negative interval and passes a bounded
image/post phase audit. A 2,000-update run still fails fixed event-F1 thresholds;
10,000 updates pass them with 1.0 hold/press/release F1 and state/axis-bin accuracy
on the training windows. Both attempts are retained. The [frozen reserved-match
evaluation](../../docs/heldout-image-evaluation.md) now handles swapped physical
ports and exposes failed generalization: hold/press/release F1 is 0.0187/0/0.
The image-only training regression still scores perfectly. A source-footage plus
controller-panel review MKV is retained on the V100. A six-train/two-validation
starter dataset and [resumable server-local runner](../../docs/training-control.md)
are now ready. Next: measure useful multi-match learning and expand the data,
then validate native VI/PAD adaptation and genuine replay generation. Loss
decrease or memorization does not establish those outcomes.

## Available resources and next work

No per-frame manual controller annotations or new hardware purchase is required
for this pilot. The existing ISO, official Playback and supplied replays suffice
for ongoing data/alignment work. The Arch workstation reports an Intel Arc B580;
the user supplied SSH access to the V100 server. Its isolated Docker/CUDA 12.6
environment now passes real convolution/GRU forward/backward checks and the
100-update training smoke test. The runner accepts explicit CPU/CUDA selection,
caps allocator memory and batches evaluation. See the remote report for measured
timings and limits; this does not establish useful input prediction.

The workstation filesystem had about **12 GB free after the first pilot**. The
remote workspace has about **707 GiB free after setup** and can store larger
datasets. Keep short/compressed clips and bounded decoded windows rather than
accumulating unrestricted PNG dumps. More diverse
Fox/Falco matches will be needed for measured generalization, after the existing
two-match pilot establishes timing and evaluation. Extra system RAM and the
RX 6800 XT are not needed to unblock this first model.
