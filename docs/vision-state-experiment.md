# Matched Melee vision fine-tuning experiment

The first matched pilot has completed and **passes its fixed development gates**.
The fine-tuned image encoder recognizes action and grounded/airborne state better
than the paired frozen encoder. **Controller input improvement is not established
by this experiment.** Existing controller models and all game code/math remain
unchanged.

## Data and comparison

The verified corpus supplies one first-sorted audited clip per development match,
selected without looking at state labels or model scores. Every sixth original
frame is used for this single-image experiment: **13,600 training images from
68 matches**, **5,800 validation images from 29 matches**. The 22 final-test
matches remain sealed. Original signed frame keys and image/post phase are kept;
there is no interpolation or fitted lag. Future controller features must be
encoded at the original 60 Hz rather than reusing this sparse state sample.

Both branches use the same ImageNet ResNet18 initialization, 384×320 letterboxed
RGB images, setup information, initial state head, sampled batches and update
count. The prefix through `layer3` is frozen and shared. In the `frozen` branch
the final CNN block is also frozen; in `finetuned`, only that block's parameters
are adapted. Both state heads train normally. BatchNorm running statistics remain
fixed in both branches so their updates do not confound the comparison.

Each player receives supplied character, costume and physical-port one-hot
metadata. A shared head uses that metadata to query a spatial attention map,
alongside global image features. Swapping supplied player identities swaps the
outputs by construction; no scoring labels select player assignment. Attention
is a learned diagnostic, **not validated fighter boxes or tracking**.

The targets are original action-state IDs and airborne flags with missing-value
masks. Original controller inputs/state are never image-model inputs. RGB/setup
inputs and state answers are in separate files; review freezes both branches'
predictions before loading state targets. Unknown fields stay masked.

The setup/attention head differs from the earlier controller head, so comparison
with that old model would mix several changes. The matched pair isolates final
CNN-block fine-tuning with this same head. The existing L/R/Z and button-edge
constraints remain in the controller pipeline; this vision pilot emits no inputs.

## Completed result

The pilot ran **1,000 paired updates**, batch size 64, head learning rate 0.001,
last-block learning rate 0.00003, seed 3. Validation ran every 200 updates. Best
fine-tuned action macro recall selects the paired checkpoint; the best is step
1,000, with both branches evaluated at that same update.

| Development metric | Frozen CNN | Fine-tuned final block |
| --- | ---: | ---: |
| Action accuracy | 26.53% | 37.16% |
| Action macro recall | 9.97% | 16.10% |
| Airborne balanced accuracy | 80.74% | 85.87% |
| Airborne accuracy | 81.33% | 86.53% |

There are 11,600 scored player-frames and 140 action classes in validation.
Macro recall averages recall over present action classes; it exposes a model
that succeeds mostly on common states. Rare classes can make it noisy; this is
a development comparison, without a player-disjointness or unseen-test claim.

The [fixed experiment plan](../configs/state-vision-experiment-v1.json) was saved
before the full run. It requires at least two percentage points of action macro
recall gain and no more than one point of action-accuracy or airborne-balanced
accuracy regression. Gains are **+6.12, +10.63 and +5.12 points**, respectively.
All gates pass. `results` distinguishes provisional criteria from a completed
pilot and never marks controller improvement as established.

## Running and reviewing it yourself

Everything is on `prompter@10.12.0.10`. The new `~/train-vision` command selects
[`configs/vision-v100-state.json`](../configs/vision-v100-state.json):

```bash
~/train-vision status
~/train-vision results
~/train-vision prepare
~/train-vision start
~/train-vision pause
~/train-vision resume
~/train-vision stop
~/train-vision logs --follow
~/train-vision review --best
```

The pilot has finished; `start` at its existing 1,000-step limit preserves the
checkpoint and exits. `start --steps <larger-total>` can continue the same
experiment. Do not change the model/objective/data contract while resuming it.
`~/train-melee` still selects the completed controller run. Run identity labels
prevent one command from accidentally pausing or overwriting the other active
training run. The shared GPU roles allow one preparation/training/review workload
at a time.

Preparation creates about 7.2 GB of uint8 RGB caches and separate state targets,
verifying source PNG/view/label identities. It retains all original game assets
and footage. Workers are detached, use the selected V100, have networking disabled
and restart policy `no`; the workstation/SSH session can be off. The existing
encoder weights are loaded from the local Torch cache, without downloading.

V100 paths:

```text
/home/prompter/yt2slp/.docker-state/local/state-vision-v1/                    RGB/targets
/home/prompter/yt2slp/.docker-state/local/vision-training/state-vision-v1/   run
  checkpoints/step-*.pt             both branches, optimizers and RNG state
  best.json / latest.json           checksum-bound model pointers
  metrics.ndjson                   full paired validation history
  experiment-plan.json              fixed gates copied before production updates
  experiment-result.json            measured result and gate decisions
  reviews/                         recorded/frozen/fine-tuned state MP4/MKV
```

The frozen prefix is reconstructed from the server-local
`.docker-state/cache/torch/hub/checkpoints/resnet18-f37072fd.pth`; its checksum and
runtime/source identities are in the training contract. The paired checkpoint
contains the adapted block and state head, rather than being a standalone video
to replay model.

Review compares original footage, recorded states, frozen predictions and
fine-tuned predictions. It uses two fixed roster-balanced validation clips at
10 sampled frames/second, with diagnostic attention thumbnails. These are state
reviews, without reconstructed gameplay or generated controller inputs.

## Validation and remaining integration

Docker checks pass 456 core tests and 34 optional model/trainer tests. They cover
one-to-one event matching, split isolation, supplied-identity equivariance,
frozen/fine-tuned gradient separation, fixed BN, masked labels, RGB/answer file
separation, wrong-run control protection and exact CPU resume of both branches,
optimizers, sampler and random state.

The real CUDA lifecycle pauses at 170, resumes and stops at 240 on an isolated
four-clip cache. Both state reviews fully decode. Direct weight checks confirm
the frozen last block is unchanged, 15 fine-tuned parameter tensors changed and
BN statistics stayed fixed. Old controller checkpoint pointers/payloads still
verify. Smoke evidence is under
`vision-training/state-vision-v1-smoke/controller-validation.json`.

The completed full run also passes source/dataset/checkpoint checksums, frozen
weights and BN checks, four exact original-PNG/RGB/normalization samples, and
full decoding of both 200-frame/10-FPS review MP4s. Attempts to change the fixed
gate plan after launch are rejected. The receipt is
`vision-training/state-vision-v1/validation.json`.

Final V100 reviews are under
`vision-training/state-vision-v1/reviews/review-1792883109301399401/`. MP4/result
copies on the workstation are in `.docker-state/local/state-vision-v1-review/`:

- `validation-01-023af3908c0f/state-review.mp4` (Fox–Fox).
- `validation-02-04f3877e9e8d/state-review.mp4` (Fox–Falco).

Next, freeze this encoder/checkpoint, encode the full original 60 Hz views, and
train/evaluate a new constrained controller model with explicit player setup.
Keep label-free image inference and all original frame/port keys. Only then can
controller event F1 and simulator-validated movement establish whether this
state-recognition gain improves reconstruction. Tracked pixel boxes, broader
vision conditions and full native/official parity remain open.
