# Completed controller-model error analysis

The held-state `sequence-v1` run completed 20,000 updates. Its best full
development checkpoint is step 16,000: hold/press/release F1
0.24679/0.04117/0.01998, mean 0.10265. The final mean is 0.09733. All button and
digital shoulder/Z outputs obey their constraints; correct input recognition is
still unestablished.

The new diagnostic reproduces the saved best checkpoint's TP/FP/FN counts exactly
over all 55 validation clips and 64,295 scored windows. Per-clip predictions are
frozen before accessing the cached state/control answers. Final-test matches stay
sealed. This is development analysis, not a new unseen evaluation.

## Findings

| Event | Correct predictions | False predictions | Missed events | Exact F1 |
| --- | ---: | ---: | ---: | ---: |
| Hold | 25,834 | 135,534 | 22,161 | 0.24679 |
| Press | 460 | 16,411 | 5,015 | 0.04117 |
| Release | 223 | 16,624 | 5,247 | 0.01998 |

Only 2.7% of predicted presses match exactly. L/R contribute 4,879 false presses;
Y contributes 3,765. Wrong held shoulder states also force wrong effective trigger
values, even though the mechanical coupling rule remains correct.

Permissive one-to-one timing matches give:

| Allowed timing distance | Press F1 | Release F1 |
| --- | ---: | ---: |
| Exact frame | 0.04117 | 0.01998 |
| Within one frame | 0.09514 | 0.05780 |
| Within two frames | 0.13452 | 0.09473 |

Each event can match once, within its own clip, physical player and button.
These diagnostic matches do not shift predictions or fit an image/input phase.
High false-positive density can also create nearby matches by chance; the table
does not establish a global timing error or justify relaxing replay acceptance.

A fixed held-logit offset of `log(training_positive_weight)` was declared before
scoring, using training counts only. It reduces false holds but collapses recall:
hold/press/release F1 becomes 0.08539/0.01194/0.00808. It is a diagnostic rather than
an exact probability correction under the combined edge loss. No threshold was
fitted, and the offset is not deployed to the existing controller model.

Always swapping physical output slots also worsens press F1 to 0.03813. A single
global reversal does not explain the errors. Individual clip permutation results
are retained for diagnosis only; no answer-selected assignment enters inference
or reported primary metrics. The original network receives images but no explicit
costume-to-port setup, motivating a setup-conditioned vision experiment without
claiming that identity confusion alone caused its errors.

## Retained report and next experiment

V100 output:

```text
/home/prompter/yt2slp/.docker-state/local/error-analysis-sequence-v1/
  report.json                    per-button, timing, threshold and slot diagnostics
  model-snapshot.pt              checksum-bound best checkpoint copy
  predictions-*.pt               frozen image-feature-only outputs
```

The report JSON is also copied to the workstation at
`.docker-state/local/error-analysis-sequence-v1/report.json`.

The CLI is `tools/learning/diagnose_sequence.py --config
configs/vision-v100-sequence.json --output <new-directory>` in the V100 Docker
environment. It never updates the model, original corpus or controller defaults.

The [matched visual-state pilot](vision-state-experiment.md) tests whether adapting
the image encoder helps. It improves development state recognition. That gain
must still be carried into a separate 60 Hz controller run and evaluated with the
existing button/trigger constraints before claiming better input reconstruction.
