"""Constraint gradients, image-only decoding and durable sequence-run lifecycle."""
from copy import deepcopy
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import torch
from baseline import AXES, BUTTONS, targets_for_frames
from runtime_files import atomic_json, read_json
from sequence_data import SequenceStore
from sequence_model import SequenceProposal, hard_controls, proposal_rows, sequence_loss, sequence_metrics
import test_corpus_training as corpus_fixture
import train_sequence
from yt2slp.sequence_controls import decode_sequence, trigger_rule


def targets():
    frames = []; previous = (0, 0)
    for number, masks in enumerate(((0, 1024), (64, 0), (64 | 16, 256))):
        rows = []
        for port, mask in enumerate(masks):
            rule = trigger_rule(mask)
            rows.append({'physical': {'values': {'buttons': mask}, 'mask': {'buttons': True}},
                'physical_edges': {'pressed': mask & ~previous[port], 'released': previous[port] & ~mask, 'mask': number > 0},
                'effective': {'values': {**dict.fromkeys(AXES, 0.), 'trigger': rule[0] if rule else .5}, 'mask': dict.fromkeys(AXES, True)},
                'state': {'values': {'action': 24, 'airborne': False}, 'mask': {'action': True, 'airborne': True}}})
        frames.append({'targets': rows}); previous = masks
    return {k: v.unsqueeze(0) for k, v in targets_for_frames(frames).items()}


class SequenceModelTests(unittest.TestCase):
    def setUp(self): torch.set_num_threads(1)

    def test_gradients_reach_held_axes_and_auxiliary_heads(self):
        model = SequenceProposal(8, 8); prediction = model(torch.randn(1, 3, 5, 8))
        self.assertEqual(prediction['held'].shape, (1, 3, 2, 12))
        loss, parts = sequence_loss(prediction, targets(), torch.ones(2, 3, 12)); loss.backward()
        self.assertTrue(torch.isfinite(loss))
        for parameter in model.parameters():
            self.assertIsNotNone(parameter.grad); self.assertTrue(torch.isfinite(parameter.grad).all())
        self.assertEqual(set(parts), {'buttons', 'axes', 'action', 'airborne'})

    def test_no_independent_edge_heads_and_hard_controls_always_valid(self):
        model = SequenceProposal(8, 8)
        self.assertFalse(any('button_heads' in name for name, _ in model.named_parameters()))
        prediction = model(torch.randn(1, 3, 5, 8)); prediction['held'] = torch.full_like(prediction['held'], -9.)
        prediction['held'][0, 1, 0, list(BUTTONS).index('l')] = 9.
        prediction['held'][0, 2, 0, list(BUTTONS).index('z')] = 9.
        buttons, axes = hard_controls(prediction)
        self.assertEqual(axes[0, :, 0, 4].tolist(), [16, 6])
        self.assertTrue(buttons[0, 0, 0, 0, list(BUTTONS).index('l')])
        self.assertTrue(buttons[0, 0, 0, 1, list(BUTTONS).index('l')])
        metrics = sequence_metrics(prediction, targets())
        self.assertEqual(metrics['constraint_metrics'], {'invalid_button_frames': 0, 'invalid_trigger_frames': 0})

    def test_hard_tensor_and_label_free_artifact_decoding_agree(self):
        torch.manual_seed(8); model = SequenceProposal(8, 8)
        prediction = model(torch.randn(1, 4, 5, 8)); buttons, axes = hard_controls(prediction)
        frames = [{'replay_frame': i+100, 'index': i+15} for i in range(4)]
        rows = proposal_rows(prediction, frames, [3, 1], [2, 20])
        decoded = decode_sequence({'kind': 'frozen-image-held-state-proposals', 'rows': rows,
            'slot_ports': [3, 1], 'prediction_interval': [100, 103], 'context_frames': 31})
        for i, row in enumerate(decoded['rows']):
            frame, slot = divmod(i, 2)
            self.assertEqual([row['axis_bins'][a] for a in AXES], axes[0, frame, slot].tolist())
            for h, head in enumerate(('hold', 'press', 'release')):
                expected = sum(bit for bit, value in zip(BUTTONS.values(), buttons[0, frame, slot, h]) if value)
                self.assertEqual(row['buttons'][head], expected)

    def test_rejects_contradictory_edges_or_trigger_labels(self):
        model = SequenceProposal(8, 8); prediction = model(torch.randn(1, 3, 5, 8))
        bad = targets(); bad['buttons'][0, 1, 0, 1, 0] = 1.
        with self.assertRaisesRegex(ValueError, 'edges disagree'): sequence_loss(prediction, bad, torch.ones(2, 3, 12))
        bad = targets(); bad['axes'][0, 1, 0, 4] = 0
        with self.assertRaisesRegex(ValueError, 'trigger label'): sequence_loss(prediction, bad, torch.ones(2, 3, 12))

    def test_deterministic_trigger_branch_has_no_conditional_head_gradient(self):
        model = SequenceProposal(8, 8); prediction = model(torch.randn(1, 3, 5, 8)); prediction['axes'].retain_grad()
        loss, _ = sequence_loss(prediction, targets(), torch.ones(2, 3, 12)); loss.backward()
        self.assertEqual(float(prediction['axes'].grad[0, 1:, 0, 4].abs().sum()), 0.)
        self.assertGreater(float(prediction['axes'].grad[0, 1:, 1, 4].abs().sum()), 0.)

    def test_masked_labels_contribute_zero_and_extreme_logits_remain_finite(self):
        model = SequenceProposal(8, 8); prediction = model(torch.randn(1, 3, 5, 8)); masked = targets()
        for key in masked:
            if key.endswith('_mask'): masked[key].zero_()
        loss, _ = sequence_loss(prediction, masked, torch.ones(2, 3, 12)); self.assertEqual(float(loss.detach()), 0.)
        prediction['held'] = torch.tensor([-1000., 1000.]).repeat(1, 3, 2, 6).requires_grad_()
        loss, _ = sequence_loss(prediction, targets(), torch.ones(2, 3, 12)); loss.backward()
        self.assertTrue(torch.isfinite(loss)); self.assertTrue(torch.isfinite(prediction['held'].grad).all())


class SequenceTrainingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = corpus_fixture.CorpusTrainingTests(); self.fixture.setUp(); self.root = self.fixture.root
        self.root_patch = patch.object(train_sequence, 'ROOT', self.root); self.root_patch.start()
        original = Path(__file__).resolve().parents[2]
        for name in ('sequence_controls.py', 'button_decoder.py', 'prediction_scoring.py'):
            shutil.copy2(original/'src/yt2slp'/name, self.root/'src/yt2slp'/name)
        self.config = {**self.fixture.config, 'pipeline': 'sequence-v1', 'sequence_frames': 2}

    def tearDown(self): self.root_patch.stop(); self.fixture.tearDown()

    def payload(self, run): return self.fixture.payload(run)

    def test_sequence_boundaries_include_seed_and_never_cross_clips(self):
        store = SequenceStore(self.fixture.manifest, 'train', 2, resident_clips=1)
        self.assertEqual(store.total, 6); features, target = store.batch([2, 3])
        first = store.load(0)['features']; second = store.load(1)['features']
        self.assertEqual(features.shape, (2, 3, 3, 3072))
        torch.testing.assert_close(features[0, 0], first[2:5]); torch.testing.assert_close(features[0, -1], first[4:7])
        torch.testing.assert_close(features[1, 0], second[:3])
        with self.assertRaises(ValueError): store.batch([6])

    def test_resumed_model_optimizer_sampler_rng_and_validation_are_exact(self):
        whole, split = self.root/'whole-seq', self.root/'split-seq'
        train_sequence.train(self.config, whole, 'cpu', 8)
        train_sequence.train(self.config, split, 'cpu', 3); train_sequence.train(self.config, split, 'cpu', 8)
        a, b = self.payload(whole), self.payload(split)
        for key in ('model', 'optimizer', 'sampler_rng', 'torch_rng', 'validation', 'best_score'):
            self.fixture.equal(a[key], b[key])
        self.assertEqual(a['validation']['constraint_metrics'], {'invalid_button_frames': 0, 'invalid_trigger_frames': 0})

    def test_pause_stop_and_objective_contract_guards(self):
        run = self.root/'sequence-pause'; atomic_json(run/'control.json', {'command': 'pause'})
        train_sequence.train(self.config, run, 'cpu', 4)
        self.assertEqual(self.payload(run)['step'], 0); self.assertEqual(read_json(run/'status.json')['state'], 'paused')
        atomic_json(run/'control.json', {'command': 'run'}); train_sequence.train(self.config, run, 'cpu', 4)
        atomic_json(run/'control.json', {'command': 'stop'}); train_sequence.train(self.config, run, 'cpu', 8)
        self.assertEqual(self.payload(run)['step'], 4)
        self.assertEqual(read_json(run/'status.json')['state'], 'stopped')
        with self.assertRaisesRegex(ValueError, 'changed'):
            train_sequence.train({**self.config, 'sequence_frames': 3}, run, 'cpu', 8)


if __name__ == '__main__': unittest.main()
