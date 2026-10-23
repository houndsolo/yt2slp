# First learned reconstruction baseline

The next milestone is paired-data construction and a small temporal model.
Manual controller grids have validated simulation, checkpointing and genuine
playback. They are not a scalable strategy for real matches. A dash, short hop,
laser and fast-fall involves coordinated direction changes, button edges and
holds across time; longer play multiplies the possible sequences.

Do not postpone learning until that opening is manually solved. A first CPU
optimizer smoke test ran on a provisional paired training clip. The signed-frame
follow-up now passes a bounded timing audit and a training-clip overfit sanity
check on the V100. No useful held-out input reconstruction is established. Correct timing and
whole-match evaluation remain prerequisites for scaling, rather than complete
native parity or a perfect hand-authored controller grid.

## Implemented pilot

The [executable baseline](../tools/learning/README.md) exports original pre-frame
controls, separate physical fields, press/release edges and masked post-state
labels without account metadata. It binds these to the prepared official MP4's
replay/video/image identities and original 60 Hz timestamps. A frozen whole-match
and capture-date split reserves another Fox/Falco Battlefield match for validation.
Cross-date player separation is unknown.

The initial training clip has 180 images, 360 player-frame labels and 150 31-frame
windows. A frozen pretrained ResNet18 plus small bidirectional GRU predicts button
hold/press/release probabilities, categorical effective axes and auxiliary state.
100 CPU updates reduce training loss 10.51 → 1.84, but training edge F1 remains
only 0.048/0.043. This verifies the data/optimizer path, not accurate recognition,
successful overfitting, unseen-match performance or simulator integration.

The [signed-frame follow-up](signed-training-data.md) includes 241 images at
−60..180, with every signed UI index verified and all 180 positive HUD labels
independently agreeing. Original/official nine-field comparisons pass across
482 player-frames. Seven reviewed ground/air observations support zero image/
post phase locally; ambiguous foot animation and occluded observations remain
unknown, with the first failed audit retained.

Its 211 temporal windows include Falco's opening. The first 2,000-update run
fails the predeclared event thresholds despite accurate state/stick predictions;
10,000 updates pass the same 0.95 thresholds with 1.0 training hold/press/release
F1 and state/axis-bin accuracy. This is memorization, not unseen-match accuracy.
The native VI adapter remains unverified and no learned proposal has generated
a replay yet.

## Data and timing

Render supplied training replays with official Playback and bind frames to replay
identities, settings, code configuration and game-frame labels. Export training
targets from original pre-frame controller events and post-frame game state.
The [Slippi format](https://github.com/project-slippi/slippi-wiki/blob/master/SPEC.md)
provides controller fields, action state, positions and grounded/airborne state.
Keep processed/effective controls distinct from raw physical fields; retain
missing-field masks rather than inventing raw values.

The rendered timer is not by itself proof that image, post-state and effective
input have identical phase. Calibrate their association with known button edges
and visible transitions before scaling exports. Separately measure the adapter
from effective replay-frame controls to native VI PAD requests; do not silently
copy a frame index across that input pipeline. Preserve one/two-frame press and
release events and original video timestamps.

Split by whole match and, where practical, player/session before sampling
overlapping clips. Neighboring frames of one match must not cross train/test
boundaries. The supplied examples can bootstrap the pipeline and a narrow pilot;
their sufficiency for generalization must be measured. The already examined
opening is a development case, not an unseen test.

Training replays intentionally supply original controls and state as labels.
Held-out replay controls/state are unavailable to inference and candidate
selection; use them only for subsequent evaluation. This is the distinction
between supervised training and copying an evaluation replay.

## Model and simulator roles

Start with Fox/Falco on a declared stage/configuration. Use windows of gameplay
frames, known roster/ports and a pretrained image encoder with a small temporal
head. Whole gameplay frames avoid requiring an unimplemented camera-to-screen
projection or automatic fighter-box annotation in the first baseline. Player
localization/crops can be added with separately validated labels later.

Predict per-player buttons/press-release timing and stick distributions, with
auxiliary action-state and ground/air targets. Use past and future context for
offline reconstruction. Predict several plausible sequences: visually equivalent
X/Y choices or redundant held buttons cannot always be uniquely recovered.
Compound actions should emerge from sequences and their labels; avoid enumerating
every dash/jump/attack/fast-fall combination by hand.

The model supplies input proposals and visual-state evidence. Native simulation
keeps several plausible branches, checks their motion and refines timing. Carry
verified history forward; retain uncertainty and backtrack when later evidence
conflicts. Official Playback remains the final generated-replay validation.
Model predictions do not bypass unsupported-code or simulation-compatibility gates.

## First experiments and acceptance

1. Completed for this bounded pilot: audit signed images and local image/post
   phase, including playable pre-clock frames. General timing and native VI/PAD
   adaptation remain separate work.
2. Completed: overfit one short **training** clip with event-sensitive criteria.
   Completed first frozen reserved-match evaluation with explicit swapped-port
   mapping: useful recognition fails (hold F1 0.0187, press/release F1 zero).
   The same inference code retains perfect training metrics. The expanded
   six-train/two-validation starter set and [server-local training controls](training-control.md)
   are now ready, with frozen whole-match/date splits and indexed feature loading.
   Next: measure useful multi-match learning and expand the data according to
   failures. Keep neutral baselines alongside event metrics so missed transitions
   remain visible, and preserve the separate unseen test groups.
3. Measure button/edge accuracy, stick error, action/ground-air predictions and
   event timing, including short/full hops and dash/short-hop/laser/fast-fall.
4. Reconstruct held-out short windows using model proposals and simulator checks.
   Evaluate motion, continuity and actual rendered replay similarity; exact input
   identity alone is insufficient when multiple programs produce the same motion.
5. Expand match/character/stage coverage and training data according to failures.
   Add compression, overlays and other appearance differences before claiming
   transfer from official renders to tournament/YouTube video.

A first small model can target the available RTX 3080 10 GB or V100, with measured
batch sizes and optional cached encoder features. Pin and smoke-test a V100-
compatible PyTorch/CUDA build; some newer binaries
[omit Volta support](https://dev-discuss.pytorch.org/t/dropping-volta-support-from-cuda-12-8-binaries-for-release-2-11/3290). Larger-run GPU memory,
training throughput and accuracy estimates remain unmeasured; the pilot has measured
allocator/RAM usage and timings. Multi-GPU or mixed
NVIDIA/AMD training is not a prerequisite for this initial experiment.
The current checkout's host exposes an Intel Arc B580 instead. The user has now
provided SSH access to the V100 server: [remote setup](remote-training.md) records
an isolated Docker/CUDA 12.6 environment, real GPU forward/backward checks and a
successful 100-update smoke run, with about 707 GiB free disk. The existing LLM
containers were stopped and their restart policies disabled at the user's request.
No additional system RAM is needed for the exercised pilot; measure larger-run
memory after timing/data correctness is established.
