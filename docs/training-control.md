# Running training yourself on the V100

Everything needed by this runner lives on **the V100 server**: checkout, Docker
images, pinned PyTorch environment, official Playback, ISO, replays, calibrations,
prepared features, logs and checkpoints. The workstation can be shut off. Workers
run detached with Docker networking disabled; neither Codex nor an open SSH
connection is required. Keep the V100 server powered on.

Connect, then open the menu:

```bash
ssh -F /dev/null prompter@10.12.0.10
~/train-melee
```

`~/train-melee` is a symlink to the checked-in executable
`/home/prompter/yt2slp/scripts/train-v100.sh`. The equivalent direct commands are:

```bash
~/train-melee start            # start, or continue the latest checkpoint
~/train-melee status           # current state, progress, validation F1, checkpoint
~/train-melee logs --follow    # live logs; Ctrl-C closes only the viewer
~/train-melee pause            # save, exit and release GPU memory
~/train-melee resume           # restore model + optimizer + sampler/random state
~/train-melee stop             # save and exit, labelled stopped
~/train-melee doctor           # check installed paths, images and visible GPUs
```

Start and resume are equivalent. Pause and stop both save progress; their status
labels express your intent. They wait up to 55 seconds for the worker to save and
exit. A pending message means the request remains active; use `status` again.
The worker checks requests between complete optimizer updates. An in-progress
validation batch sequence finishes before saving. Closing SSH never sends a stop
request to the detached worker.

Default training is bounded at **100,000 total optimizer steps**. To change the
limit without resetting progress:

```bash
~/train-melee start --steps 200000
```

This means step 200,000 including saved steps, not 200,000 additional steps. A
completed run resumes only if its total limit is increased. Validation runs every
1,000 steps; the mean of hold/press/release F1 selects the best checkpoint. A
lower training loss is not proof of better recognition. Inspect validation F1 and
axis/state metrics, including neutral baselines, in the saved metrics.

## What is being trained

This is the narrow **Fox/Falco Battlefield** model. A frozen pretrained ResNet18
encodes each whole image into 3,072 spatial features. The trainable projection,
bidirectional GRU and controller/state heads read 31-frame windows and predict
their centers. Known character IDs map output slots to physical ports. Input
windows remain inside their original matches. Doubles, mirrors and other
rosters/stages are outside this runner's current dataset contract.

The starter selection is **six training matches and two validation matches**,
with separate filename-date groups. The two previously prepared pilot clips have
241 images each; six new clips request −60..600, 661 images each. Prepared
features are memory mapped and only minibatch windows are materialized. The
pilot's eager allocation of every overlapping window is not used here.

The larger frozen plan has 34 training, 14 validation and 10 test candidates.
Preparation opens only the selected train/validation sources; **test replays are
not rendered or labelled**. Dates are filename heuristics; player-disjointness
is unverified. Validation is used for model selection and is not an unseen test.

The completed starter dataset has **4,448 images**, **3,366 training windows**
and **842 validation windows**. Its capture audits agree on 3,960 positive HUD
labels and nine original/official state fields across 8,896 player-frames.

Official Playback runs unchanged in a separate rendering image using Xvfb/Mesa.
Each new clip must pass exact signed UI progression, one clean PNG per step,
all positive-clock HUD labels and the nine-field original/official comparison.
Image/post phase uses the explicitly transferred zero convention from the
independently reviewed training clip. New clips are not claimed to have separate
manual ground/air boundary reviews. This is an experimental expanded dataset.
Native VI/PAD adaptation, useful generalization and learned replay generation
remain separate project gates. Training produces model checkpoints, not `.slp` files.

This cached-feature model is small. Its runtime should be judged from the
measured steps/second and validation curve; it does not inherently need days of
GPU time. Adding diverse, audited training footage matters more than repeatedly
training on the same short clips. Encoder fine tuning and larger datasets can
be evaluated later. No extra system RAM is required by this starter setup.
A short V100 run measured approximately **43 updates/second** with batch size 32:
100,000 updates would take about **40 minutes at that rate**. This is a cached-
feature throughput estimate, not a promise of recognition quality or convergence.

## Files, recovery and expanding the data

The default configuration is
[`configs/vision-v100.json`](../configs/vision-v100.json). All paths are relative
to `/home/prompter/yt2slp`, including the user's **`recordings/vanilla.iso`**.
The V100's single selected GPU is
`GPU-ce8ddd39-0bf5-1021-dbe2-221ddcb9ece5`; the GT 1030 is not used.

```text
.docker-state/local/vision-data-v1/
  selection.json                frozen source selection
  preparation-status.json       current clip or actionable failure
  clips/<replay-sha>/            feature shard, identities, retained capture attempts
  dataset.json                  published only after every selected clip succeeds

.docker-state/local/vision-training/default/
  status.json                   human controller reads this
  control.json                  atomic pause/stop requests
  contract.json                 dataset/runtime/source/hyperparameter identity
  metrics.ndjson                validation history
  latest.json                   checksum-bound latest checkpoint pointer
  best.json                     best validation checkpoint pointer
  checkpoints/                  latest, previous and best generations
```

Checkpoints contain model parameters, AdamW state, step, best validation score,
PyTorch CPU/CUDA random states and the window sampler state. The trainer writes
and flushes a new generation before atomically publishing its pointer. It keeps
the previous generation and best validation generation. A killed process or
power loss resumes from the last complete checkpoint; updates since that save
may be lost. Checksum or contract mismatches fail visibly instead of silently
starting over. Copies of old checkpoint generations can be retained separately
before deliberate recovery or migration.

After a V100 **server** reboot, run `~/train-melee resume`. Automatic restart is
disabled so rebooting does not unexpectedly start a GPU workload. Docker and the
NVIDIA driver must be available. The older LLM containers remain stopped with
their restart policies disabled; this runner does not remove their data.

Data preparation also has a detached control:

```bash
~/train-melee prepare
~/train-melee logs --preparation --follow
~/train-melee stop-preparing
~/train-melee prepare          # reuse completed shards, retry unfinished/failed clips
```

Preparation and training are mutually exclusive under the controller. Failed
capture attempts are retained, never promoted to a ready dataset. Dependencies,
encoder weights and calibrations are already local. To rebuild the rendering
image later, the Docker build needs access to Debian package sources:

```bash
cd ~/yt2slp
docker build -f docker/Dockerfile.render -t yt2slp-render:gcc14 docker
```

To expand the frozen candidate plan, copy the config to a new file and give it
**new `data_directory` and `run_directory` values**, then increase match counts
or `prepare_last_frame` (up to 1,800). Use `--config configs/your-file.json` with
prepare/start/status. Keep the frozen test dates reserved. Existing runs refuse
changed dataset identities or learning hyperparameters; changing a long-running
experiment requires an explicit new run rather than silently altering its data.
Game assets, imported replays, model weights and generated artifacts stay ignored.

## Validation scope

Optional tensor tests verify exact CPU equality between resumed and uninterrupted
training, including optimizer and sampler state. They also check durable pointer
behavior under a simulated save failure, checkpoint/contract corruption, pause/
stop exits, lazy clip boundaries and split leakage. Separate V100 integration
checks exercise detached CUDA training and the actual controller commands.
CPU equality is not a cross-hardware CUDA bitwise-equality claim.

Actual controller validation passed detached CUDA start, progress after SSH exit,
pause at step 3,255, resume/stop at 4,657, and resume/pause at **7,691**. The
handed-over run is paused; the final container exited with status zero and the
V100 reported 0 MiB used / 32,495 MiB free. Its final displayed validation
hold/press/release F1 is **0.1175 / 0.0513 / 0.0400**, with best validation event
F1 mean 0.09576. These are weak development metrics; useful recognition and
generalization are unestablished. `best.json` preserves the best observed model
while `latest.json` preserves the resumable current state.

Ignored evidence is in V100 `.docker-state/local/vision-control-validation/`:
`dataset-audit.json`, `lifecycle.ndjson` and `controller-validation.json`.
Docker checks pass 412 Python tests, 14 optional model/trainer tests and 17
parser/preparation/export/catalog tests. Native game code/math is unchanged;
native suites were not rerun for this milestone.

Docker's default 64 MiB `/dev/shm` caused official Playback's savestate thread to
fault before capture. The renderer now has **512 MiB shared memory**. Full UI
screenshots also made remote stepping slow; capture keeps the original-coordinate
182×35 UI corner using Pillow's XCB capture where available, with full clean
gameplay PNGs retained separately. It waits for the PNG's final IEND chunk before
hashing a dump: a filename can appear while the renderer is still writing it.
Console
sampling can alternate between zero and one frame ahead of the UI; the new
explicit per-step policy verifies each observed relation, while exact UI/PNG/HUD
checks remain mandatory. The earlier fixed-relation failures are retained. None
of these changes alter game timing, physics or arithmetic.

The original short-clip HUD calibration lacked main-clock digits 2, 3 and 4.
Three literal screenshot readings, 07:54.68, 07:53.68 and 07:52.68, extend its
ten retained original anchors. The resulting calibration and all 13 source
images live under `.docker-state/local/vision-timer-calibration-v2/` on the
server. Recognition thresholds and exact frame/state checks were kept fixed.
