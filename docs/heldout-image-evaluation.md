# First reserved-match image-model evaluation

The model memorizes its training clip and fails to predict useful controls on
the reserved clip. This is a completed diagnostic evaluation, not a learned
reconstruction. No model-generated replay or gameplay comparison exists yet.

The checkpoint is the unchanged 10,000-update signed-training model, SHA-256
`592671ba8445211958c03f3dc85f0b18bb72fb8b1121b4e11a00fe3c3299f1f0`.
Its descriptor binds training-pair/report identities, architecture, vocabulary,
encoder weights, preprocessing source, runtime versions and a zero-logit threshold.
The [two-match split](../configs/learning-pilot-split-v1.json) was declared before
this evaluation. June 23 is now an examined validation match and must not later
be described as an unseen test. Player separation across dates is unverified.

## Source preparation and separation from inference

Validation source: `recordings/examples/Game_20260623T163435.slp`, SHA-256
`35f1c56f2c5ac6ceeb74ff5144d923443bf34251d4404802408c28e577a48ae7`.
Official Playback 3.5.2 produced 241 images at signed frames −60..180. Every
retained UI index was redecoded; all 180 positive HUD labels agree. Nine selected
original/official post-state fields match across 482 player-frames. Those state
checks validate capture, not the learned predictions or native backend parity.

The zero image/post phase is **transferred from the training capture audit**,
with matching known stage/roster and the same signed UI/HUD/PBO procedure. This
clip has no independently reviewed ground/air boundary audit. The transfer has a
distinct `image-post-phase-reference` report and explicitly marks independent
target review false. It cannot pass the stronger training-pair phase gate. No
validation-label lag search or offset adjustment was performed.

The frozen model and evaluation protocol were saved before scoring controls.
`build_inference_view.py` projects images, hashes, timestamps/frame keys and
supplied stage/roster into a view without target rows. `predict.py` has no label
argument, optimizer or fitting step. Only pixel features enter the network;
frame IDs/PTS key its outputs. Known external character IDs map trained slots
Fox/Falco to physical ports **[1, 0]**, using setup rather than ground-truth
matching. No image flip or validation-label assignment optimization is applied.
Mirrors, doubles and other rosters/stages are rejected by this narrow contract.

Predictions were saved and hashed before `export-training.cjs` created the
separate scoring labels. Scoring uses exact signed frame/physical-port keys,
missing-value masks, the fixed threshold and fixed phase. Each 31-frame window
predicts its center; the first/last 15 frames supply context only. There are
211 predicted centers at −45..165, or 422 player-frame predictions.

## Measurements

| Metric | Training regression | Reserved clip | Neutral baseline on reserved clip |
| --- | --- | --- | --- |
| Button hold F1 | 1.000 | 0.0187 | 0 |
| Button press F1 | 1.000 | 0 | 0 |
| Button release F1 | 1.000 | 0 | 0 |
| Main-stick X bin accuracy | 1.000 | 0.3626 | 0.5071 |
| Main-stick Y bin accuracy | 1.000 | 0.3270 | 0.4384 |
| C-stick X / Y bin accuracy | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 |
| Trigger bin accuracy | 1.000 | 0.7654 | 0.7701 |
| Action-state accuracy | 1.000 | 0.0948 | Not scored |
| Ground/air accuracy | 1.000 | 0.5142 | Not scored |

Reserved holds: 2 true positives, 15 false positives, 195 false negatives;
presses: 0/0/20; releases: 0/0/19. The C-stick is always neutral in these scored
validation frames, so its perfect score supplies no evidence of event recognition.
Main-stick X/Y mean absolute errors are 0.6031/0.6743 in normalized units.

The same image-only inference/decoder/scorer on the training video reproduces
all previous perfect event/state/bin metrics, with 146 hold, 19 press and 19
release positives and zero false positives/negatives. Perfect bin accuracy
still quantizes analog values: training main-stick X/Y MAE is 0.00634/0.01001.
Independent hold/press/release heads need not form a consistent input sequence;
their scores are uncalibrated. They are not ready to drive native PAD requests.

## Retained artifacts and review video

On `prompter@10.12.0.10`, under `/home/prompter/yt2slp/`:

```text
.docker-state/local/learning-heldout-v1/
  frozen-model.json, evaluation-protocol.json
  video/                         official source MP4, decoded images, audits
  images.json                    target-free inference view
  predictions.json               frozen before scoring-label export
  predictions-before-labels.sha256
  labels-for-scoring.json, score.json
  training-regression-*.json      explicit examined-training regression
  review/prediction-review.mkv
  review/review.json
```

The review is **source footage beside recorded/model controller panels**, clearly
labelled with generated gameplay pending. It contains 241 frames at 60 Hz, FFV1
in MKV, 1242×528, approximately 31 MB. It can be paused or stepped to inspect
errors. It is not a reconstructed-game side-by-side comparison. Successful
parser/official playback of a future learned `.slp` remains a separate gate.

For new output filenames, after preparing another compatible signed source:

```bash
# In the V100 checkout; see remote-training.md for the exact single-GPU selector.
PY=.local/learning-cu126/bin/python
bash scripts/docker.sh run "$PY" scripts/build_inference_view.py \
  --video .local/NEW-video --output .local/NEW-images.json
YT2SLP_GPU=GPU-ce8ddd39-0bf5-1021-dbe2-221ddcb9ece5 \
  bash scripts/docker.sh run env TORCH_HOME=/work/.cache/torch "$PY" tools/learning/predict.py \
  --model .local/learning-heldout-v1/frozen-model.json --view .local/NEW-images.json \
  --output .local/NEW-predictions.json --device cuda
# Only after predictions are fixed: export labels for evaluation, then score.
bash scripts/docker.sh run node tools/slippi-parser/export-training.cjs \
  recordings/examples/NEW.slp -60 180 > .docker-state/local/NEW-scoring-labels.json
bash scripts/docker.sh run "$PY" scripts/score_image_predictions.py \
  --predictions .local/NEW-predictions.json --labels .local/NEW-scoring-labels.json \
  --output .local/NEW-score.json
bash scripts/docker.sh run "$PY" scripts/render_prediction_review.py \
  --view .local/NEW-images.json --predictions .local/NEW-predictions.json \
  --labels .local/NEW-scoring-labels.json --output .local/NEW-review
```

Next: freeze a larger match/date split from the [catalog](replay-corpus.md),
render/audit bounded samples across matches and train with indexed/chunked
features. Measure useful event recognition before relying on model proposals.
Appearance/HUD shortcuts, player association and camera robustness remain
untested. Native VI/PAD adaptation and code-set compatibility remain separate.
Docker checks: 403 Python tests, eight optional model tests and 17 parser tests.
Native game math/code is unchanged; native suites were not rerun here.
