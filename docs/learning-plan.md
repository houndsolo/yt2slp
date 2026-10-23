# First learned reconstruction baseline

The next milestone is paired-data construction and a small temporal model.
Manual controller grids have validated simulation, checkpointing and genuine
playback. They are not a scalable strategy for real matches. A dash, short hop,
laser and fast-fall involves coordinated direction changes, button edges and
holds across time; longer play multiplies the possible sequences.

Do not postpone learning until that opening is manually solved. No model has
been trained yet. The immediate prerequisites for the first training run are
correctly aligned examples and an evaluation split, rather than complete native
parity or a perfect hand-authored controller grid.

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

1. Export an audited small dataset and verify render/input timing.
2. Overfit a short **training** clip as a pipeline sanity check, then evaluate
   separate whole matches. Confirm that neutral-output dominance does not hide
   missed jump, attack and fast-fall transitions.
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
[omit Volta support](https://dev-discuss.pytorch.org/t/dropping-volta-support-from-cuda-12-8-binaries-for-release-2-11/3290). GPU memory,
training throughput and accuracy estimates remain unmeasured. Multi-GPU or mixed
NVIDIA/AMD training is not a prerequisite for this initial experiment.
