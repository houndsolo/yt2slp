# Consistent button sequences from a saved model

The existing model has independent hold, press and release heads. Its raw
thresholded answers can disagree. The new decoder uses those same frozen logits
to find a consistent button sequence, without retraining or opening replay labels.
It changes only physical button masks. Effective axes, auxiliary state, frame
keys, player assignments and raw logits remain unchanged.

## Rules and scoring

For each physical port and button, keep one binary held state:

| Previous held | Current held | Press | Release |
| --- | --- | --- | --- |
| 0 | 0 | 0 | 0 |
| 0 | 1 | 1 | 0 |
| 1 | 1 | 0 | 0 |
| 1 | 0 | 0 | 1 |

A press includes held on that frame; a release has held clear on that frame.
One-frame taps, simultaneous buttons and holding through the clip end are legal.
Both initial states have equal score, because these clips start mid-match; the
chosen pre-clip held mask is recorded, not assumed released or read from labels.

Two-state Viterbi decoding finds the highest-scoring path across the **entire
contiguous clip**, including model-inference batch boundaries. Every frame's
hold/press/release logit contributes with equal fixed weight. The sum of selected
logits ranks paths exactly like the sum of Bernoulli head log-scores: the omitted
softplus terms are constant across paths. These heads were trained with positive
class weighting, so this score is **uncalibrated**, not a posterior probability.
No fitted threshold, duration prior, timing offset or label-dependent smoothing
is introduced. Ties prefer the released predecessor/terminal state.

Missing/duplicate frame keys, gaps, invalid physical ports/buttons and non-finite
logits are rejected. Different clips never share inferred state. The raw artifact
is preserved; the decoded copy records source/decoder hashes, initial masks,
changed bits and before/after contradiction counts.

This is a one-best button decoder. It does not yet produce a beam of alternative
paths, jointly decode analog controls, adapt learned inputs to native VI requests,
search simulator branches or create reconstructed gameplay/replay files. Enforcing
controller bookkeeping does not guarantee correct button timing or identify inputs
whose effects are visually indistinguishable.

## Reviews and standalone use

On the V100:

```bash
~/train-melee review --best
~/train-melee status
~/train-melee logs --review --follow
```

Corpus reviews now select the same fixed sorted, roster-balanced four validation
clips and show **recorded / raw model / constrained** button columns beside the
original footage. Analog predictions are shared by both model columns. Both sets
of predictions are frozen before scoring labels are opened. Final-test matches
remain sealed. The snapshot is copied and verified; training weights/optimizer
and best/latest checkpoint pointers are not updated.

Each clip directory contains:

- `predictions.json`: original independent zero-logit predictions and raw logits.
- `constrained-predictions.json`: valid button path and decoder provenance.
- `score.json` and `constrained-score.json`: separate exact-frame scores.
- `comparison.json`: both button metrics, changed bits and contradiction counts.
- `prediction-review.mp4` and `video/prediction-review.mkv`: three-column review.

The root `comparison.json` aggregates **only the selected review clips**, rather
than presenting them as a full-validation or unseen-test score. Repeated reviewed
windows from one match are not independent matches. Original footage includes
15 context frames at each end without predictions.

The decoder can also process a saved raw artifact independently, using the normal
development Docker image and no PyTorch or target file:

```bash
bash scripts/docker.sh run env PYTHONPATH=src python3 \
  scripts/decode_button_sequences.py \
  --predictions .docker-state/local/my-review/predictions.json \
  --output .docker-state/local/my-review/constrained-predictions.json
```

Output creation is exclusive, and already decoded artifacts are rejected. Score
the raw and decoded files against the same labels only after both are frozen.

## First measured comparison

The preserved best checkpoint at step 10,000 produced four 20-second reviews:
two Fox–Fox and two Fox–Falco clips, totaling 9,360 scored player-frames after
context edges. Fixed equal decoder weights were declared before scoring labels
were read; the results did not trigger parameter fitting.

| Button F1 | Raw | Constrained |
| --- | ---: | ---: |
| Hold | 0.25453 | 0.27164 |
| Press | 0.07364 | 0.06349 |
| Release | 0.05679 | 0.01354 |

Inconsistent button/frame predictions drop from **4,554 to zero** across 112,320
scored button/frames. Hold precision improves, but event recall falls sharply:
release true positives fall from 32 to six. Consistent bookkeeping has not solved
event recognition; these results support measuring a transition-aware training
objective rather than assuming this decoder improves every metric.

V100 artifacts:

```text
/home/prompter/yt2slp/.docker-state/local/vision-training/corpus-v3/reviews/review-1792872411936275955/
```

The four MP4s and comparison/validation reports are also copied to the workstation:

```text
.docker-state/local/constrained-reviews-v1/
  validation-01-023af3908c0f/prediction-review.mp4
  validation-02-04f3877e9e8d/prediction-review.mp4
  validation-03-023af3908c0f/prediction-review.mp4
  validation-04-04f3877e9e8d/prediction-review.mp4
```

All four MP4s fully decode: 1,200 frames each, 60 FPS, 20 seconds, 1542×528.
Snapshot/source/decoder checksums and unchanged raw logits/axes/state pass. Best
and latest checkpoint pointers, their payload checksums and the training contract
match the pre-review receipt. The worker exits zero and training remains completed.
The standalone stdlib-only Docker decoder reproduces the review artifact byte for
byte. Docker tests pass 444 core cases and 19 optional model/trainer cases, including
exhaustive-search agreement and legacy training/resume behavior. No native game
code, timing/math, encoder, training objective or saved-run contract changed.

## Training context

The completed corpus run used 186 accepted 20-second clips (62 minutes):
131 training clips across 68 matches, and 55 validation clips across 29 matches.
The remaining 114 planned clips failed preparation and were excluded; all failures
are retained. The 22 final-test matches remain reserved.

The run completed 200,000 updates. Its best **full-validation** mean button F1
was 0.12055 at step 10,000, among evaluations every 5,000 updates. At 200,000 it
was 0.11077. Full-validation hold/press/release F1 was 0.23627/0.07520/0.05018 at
the best checkpoint and 0.23491/0.05846/0.03895 at the final checkpoint. Longer
training did not improve this metric. Decoder comparisons use the preserved best
checkpoint without fitting it again.

Useful recognition remains unestablished. The next training experiment should
compare a separately versioned transition-aware sequence objective against this
fixed decoder baseline, preserving existing checkpoint/dataset contracts.
