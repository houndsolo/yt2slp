# Training consistent controller sequences from the start

The current V100 configuration is
[`vision-v100-sequence.json`](../configs/vision-v100-sequence.json). It starts a
new **held-state sequence proposal model**, rather than continuing the old
independent-head checkpoint. The verified 186-clip corpus and frozen pretrained
ResNet18 features are reused. The old corpus model, its metrics and its best/final
checkpoints remain preserved.

This run has now completed 20,000 updates. Best at 16,000 has
hold/press/release F1 **0.24679/0.04117/0.01998**, mean 0.10265, with zero button
or trigger-rule violations. The [error report](input-error-analysis.md) and
[matched vision follow-up](vision-state-experiment.md) document the next work.

## What changed

The model predicts one held-state logit per physical button. It has no independent
press/release heads. A press is a transition from released to held; a release is
a transition from held to released. The hard output derives both from consecutive
held states, so invalid combinations cannot be emitted. One-frame taps,
simultaneous buttons and holding through the end of a clip remain legal. Each
review clip infers its own preceding state from images, rather than carrying state
between unrelated clips.

Training now samples **eight contiguous sequences of 16 supervised frames** per
optimizer step. Each sequence has one preceding image-center seed, and each of
its 17 predictions retains the same 31-frame context used at inference. Sequences
never bridge separate clips. The differentiable loss includes held states plus
press/release probabilities derived from adjacent held probabilities, with the
training-only positive class weights. Edge errors backpropagate into both
neighboring held predictions. There is no post-training Viterbi repair or
independent edge threshold in this architecture.

The effective trigger is conditional on the predicted physical buttons:

| Predicted physical buttons | Effective trigger output |
| --- | --- |
| Z held | float32 0.35, overriding digital L/R |
| L or R held, with Z released | exactly 1.0 |
| Neither Z nor digital L/R held | learned analog value |

Z priority matters. The full original-label audit found **37,413 training** and
**14,146 validation** player-frames with digital L/R held. The 306 training and
69 validation frames below trigger 1.0 all also hold Z and record exactly
`0.3499999940395355`. Every one of the corpus's **16,834 Z-held** samples records
that same value; there are no other L/R-rule conflicts. The local game source's
`Fighter_Spaghetti_8006AD10` applies the Z override after digital L/R. All
consecutive original button-edge labels agree with their held masks.

The trigger head learns its conditional analog distribution where no digital rule
fixes the value. Deterministic branches have zero conditional trigger loss;
supervision for physical L/R/Z still comes from the button losses. Contradictory
known edge/trigger labels raise an error instead of being rewritten. The original
dataset is immutable. Physical analog L/R values are separate from the effective
trigger and are not forced to one.

The 17-bin trigger target represents Z as bin 6; emitted controller reviews also
retain the exact deterministic float32 value. Other analog axes remain quantized.
No game code, timing, math, capture phase or native adapter mapping changes.

## Training limits and evaluation

The 905,028-parameter trainable model has a projection, bidirectional GRU, held-state head,
conditional axes head and auxiliary state heads. Image encoding remains frozen.
Learning rate is 0.0003, seed 2, with up to **20,000 optimizer updates**, checkpoint
saves every 500 and full development validation every 1,000. One step now includes
128 supervised center frames plus eight preceding seeds. It is not equivalent to
one batch in the earlier independent-frame run.

The completed old run peaked at 10,000 and worsened with longer training. This new
20k limit is an initial experiment; inspect validation before increasing it with
`start --steps`. The mean of derived hold/press/release F1 selects `best.json`.
Constraint correctness and useful recognition remain separate acceptance gates.
No quality improvement is claimed merely because this model's outputs are valid.

Full validation decodes each clip continuously from image-only held predictions.
Its first contextualized center seeds the state, leaving **64,295** scored
validation windows, versus 64,350 in the old run. Leading context is 16 frames;
trailing context is 15. The signed image/replay phase is unchanged. All 22 final
test matches stay sealed; no test labels or footage are added.

## Model files and controls on the V100

```text
/home/prompter/yt2slp/.docker-state/local/vision-training/sequence-v1/
  checkpoints/step-*.pt       trained model, optimizer and random state
  latest.json                checksum/path of the latest durable checkpoint
  best.json                  best validation checkpoint, after first validation
  status.json                live status, step, losses and validation metrics
  metrics.ndjson             full validation history
  contract.json              dataset, runtime, source and objective identities
  reviews/                   saved-model controller MP4/MKV comparisons
```

The saved generations retain the current, previous and best checkpoints rather
than every historical file. The old trained models remain in:

```text
/home/prompter/yt2slp/.docker-state/local/vision-training/corpus-v3/checkpoints/
```

The unchanged frozen image encoder is stored separately at
`.docker-state/cache/torch/hub/checkpoints/resnet18-f37072fd.pth`.

`~/train-melee` now selects the sequence configuration by default:

```bash
~/train-melee status
~/train-melee logs --follow
~/train-melee pause
~/train-melee resume
~/train-melee stop
~/train-melee review --best
```

Review pauses active training, copies a checksum-bound model, predicts from images,
freezes held-state proposals and constrained controls, then opens scoring labels.
The MP4/MKV shows original footage beside recorded/model controls; it does not
contain reconstructed gameplay or a generated replay. Training remains paused
after a review until `resume`. Before the first validation, use `review` to inspect
the latest saved checkpoint; `--best` needs a saved validation result.

All files, Docker images, cached footage/features, weights and dependencies remain
on the V100. The worker is detached, uses the selected GPU, and has networking and
container autostart disabled. The workstation and SSH session can be shut off.
After a server reboot, `resume` restores the durable checkpoint. Do not change
contract-bound model/data/objective files while resuming this run.

Preparation is intentionally disabled for this configuration: it reuses the
immutable corpus. Expanding footage requires a separate data/run directory. To
select the preserved previous run explicitly, use
`--config configs/vision-v100-corpus.json`; stop the active workload before
switching runs because the controller shares its GPU/container roles.

## Validation

Docker checks pass **448 core tests and 28 optional model/trainer tests**. They
cover one-frame taps, simultaneous buttons, exact trigger priority, sequence/clip
boundaries, label contradictions, masked/extreme-logit loss, gradients reaching
held-state predictions, and exact CPU model/optimizer/sampler/RNG resume.

An isolated CUDA run on four genuine cached clips pauses at step 260, resumes and
stops at 560. It reports zero invalid button/frame and trigger/frame outputs.
This is lifecycle evidence, not useful recognition. Smoke evidence lives under
`.docker-state/local/vision-training/sequence-v1-smoke/`; production training uses
the separate full-corpus `sequence-v1/` directory above.

Both smoke saved-model reviews fully decode (1,200 frames each at 60 FPS); their
button/trigger constraints pass, and old checkpoint pointers, payload checksums
and the old training contract remain unchanged. The bound evidence is
`sequence-v1-smoke/controller-validation.json`. The full-corpus run has now been
launched detached with the new default configuration, starting from fresh weights
without importing a previous checkpoint.

The full run has passed its first **1,000-step full validation**: 64,295 windows,
hold/press/release F1 **0.15673/0.01504/0.00983**, mean 0.06054. Both button and
trigger violation counts are zero; durable latest/best checkpoint files exist.
These early scores do not establish useful recognition or an improvement over
the old best model. The completed result is recorded at the top of this report.
