"""Matched branch gradients, identity equivariance and exact durable resume."""
from copy import deepcopy
from pathlib import Path
import shutil
import signal
import tempfile
import unittest
from unittest.mock import patch

from train_smoke import torch
from torch import nn
from runtime_files import atomic_json, digest, read_json
from state_data import StateStore
from state_model import StateBranch, state_counts, state_loss, summarize_counts
import train_state
import test_training as old_tests


def factory(weights):
    prefix = nn.AdaptiveAvgPool2d((4, 4)).requires_grad_(False)
    last = nn.Sequential(nn.Conv2d(3, 8, 1), nn.BatchNorm2d(8))
    frozen = StateBranch(last.requires_grad_(False), channels=8, hidden=8)
    tuned = deepcopy(frozen); tuned.last.requires_grad_(True)
    return prefix, {'frozen': frozen, 'finetuned': tuned}


class StateTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1); self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.signals = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
        self.root_patch = patch.object(train_state, 'ROOT', self.root); self.root_patch.start()
        original = Path(__file__).resolve().parents[2]
        for name in ('tools/learning/train_state.py', 'tools/learning/state_model.py', 'tools/learning/state_data.py', 'src/yt2slp/state_plan.py'):
            target = self.root/name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(original/name, target)
        self.config = read_json(original/'configs/vision-v100-state.json')
        self.config.update(data_directory='data', run_directory='run', encoder_weights='weights.pth', batch_size=2,
            threads=1, evaluate_every=4, checkpoint_every=2, log_every=100, max_steps=8)
        (self.root/'weights.pth').write_bytes(b'toy factory; no pretrained weights claimed')
        folder = self.root/'data'; folder.mkdir(); shards = []; source = []
        for index, split in enumerate(('train', 'validation')):
            clip = str(index); source.append({'clip_id': clip, 'replay_sha256': clip*64, 'split': split, 'group': split, 'frames': 4})
            inputs = {'images': torch.randint(0, 256, (4, 3, 320, 384), dtype=torch.uint8,
                generator=torch.Generator().manual_seed(index)), 'setup': torch.zeros(4, 2, 14)}
            inputs['setup'][:, :, 0] = 1; inputs['setup'][:, 0, 2] = 1; inputs['setup'][:, 1, 3] = 1
            inputs['setup'][:, 0, 10] = 1; inputs['setup'][:, 1, 11] = 1
            targets = {'action': torch.tensor([[14, 24], [24, 14], [14, 14], [24, 24]]),
                'airborne': torch.tensor([[0., 1.], [1., 0.], [0., 0.], [1., 1.]]),
                'action_mask': torch.ones(4, 2, dtype=torch.bool), 'airborne_mask': torch.ones(4, 2, dtype=torch.bool)}
            shard = {**source[-1], 'selected_indices': [0, 1, 2, 3]}
            for kind, payload in (('inputs', inputs), ('targets', targets)):
                path = folder/f'{clip}-{kind}.pt'; torch.save(payload, path)
                shard[kind] = path.name; shard[kind+'_sha256'] = digest(path)
            view = folder/f'{clip}-view.json'; atomic_json(view, {'frames': []}); shard.update(view=view.name, view_sha256=digest(view)); shards.append(shard)
        atomic_json(folder/'source.json', {'kind': 'vision-corpus-feature-dataset', 'test_matches_opened': 0, 'shards': source})
        atomic_json(folder/'dataset.json', {'kind': 'matched-state-rgb-dataset', 'source_dataset': 'source.json',
            'source_dataset_sha256': digest(folder/'source.json'), 'frame_stride': 1, 'shards': shards, 'test_matches_opened': 0})

    def tearDown(self):
        self.root_patch.stop()
        for sig, old in self.signals.items(): signal.signal(sig, old)
        self.temp.cleanup()

    def payload(self, run): return torch.load(run/read_json(run/'latest.json')['file'], weights_only=True, map_location='cpu')

    def test_matched_initial_parameters_and_only_tuned_encoder_gets_gradients(self):
        _, models = factory(None)
        for name, value in models['frozen'].state_dict().items(): torch.testing.assert_close(value, models['finetuned'].state_dict()[name])
        features = torch.randn(2, 3, 4, 4); setup = torch.randn(2, 2, 14)
        targets = StateStore(self.root/'data/dataset.json', 'train').batch([0, 1], 'targets')
        for name, model in models.items():
            model.train(); initial = model.last[1].running_mean.clone()
            loss = state_loss(model(features, setup), targets); loss.backward()
            torch.testing.assert_close(initial, model.last[1].running_mean)
            self.assertEqual(model.last[0].weight.grad is not None, name == 'finetuned')
            self.assertTrue(torch.isfinite(loss))
            self.assertIsNotNone(model.query.weight.grad)

    def test_known_setup_permutation_swaps_predictions_without_label_assignment(self):
        _, models = factory(None); model = models['finetuned'].eval()
        features = torch.randn(2, 3, 4, 4); setup = torch.randn(2, 2, 14)
        original = model(features, setup); swapped = model(features, setup.flip(1))
        for key in original: torch.testing.assert_close(swapped[key], original[key].flip(1))
        torch.testing.assert_close(original['attention'].sum((-1, -2)), torch.ones(2, 2))

    def test_input_loading_never_opens_state_answers_and_hash_changes_are_rejected(self):
        store = StateStore(self.root/'data/dataset.json', 'train')
        with patch.object(store, 'load', wraps=store.load) as read:
            store.batch([0, 2]); self.assertTrue(all(c.args[1] == 'inputs' for c in read.call_args_list))
        with self.assertRaises(ValueError): store.batch([4])
        path = self.root/'data/0-targets.pt'; path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'identity changed'): StateStore(self.root/'data/dataset.json', 'train')

    def test_macro_recall_exposes_majority_class_shortcut_and_masks_unknowns(self):
        prediction = {'action': torch.zeros(5, 2, 512), 'airborne': torch.ones(5, 2)}
        prediction['action'][..., 14] = 1
        targets = {'action': torch.full((5, 2), 14), 'action_mask': torch.ones(5, 2, dtype=torch.bool),
            'airborne': torch.ones(5, 2), 'airborne_mask': torch.ones(5, 2, dtype=torch.bool)}
        targets['action'][0, 0] = 24; report = summarize_counts(state_counts(prediction, targets))
        self.assertAlmostEqual(report['action_accuracy'], .9); self.assertEqual(report['action_macro_recall'], .5)
        for key in targets:
            if key.endswith('_mask'): targets[key].zero_()
        self.assertEqual(float(state_loss(prediction, targets)), 0.)

    def test_cpu_resumed_branches_optimizers_sampler_and_rng_are_exact(self):
        whole, split = self.root/'whole', self.root/'split'
        train_state.train(self.config, whole, 'cpu', 8, factory)
        train_state.train(self.config, split, 'cpu', 3, factory); train_state.train(self.config, split, 'cpu', 8, factory)
        a, b = self.payload(whole), self.payload(split); helper = old_tests.TrainingTests()
        for key in ('models', 'optimizers', 'sampler_rng', 'torch_rng', 'validation', 'best_score'):
            helper.assert_tree_equal(a[key], b[key])

    def test_pause_stop_and_encoder_objective_contract_guard(self):
        run = self.root/'pause'; atomic_json(run/'control.json', {'command': 'pause'})
        train_state.train(self.config, run, 'cpu', 4, factory); self.assertEqual(self.payload(run)['step'], 0)
        self.assertEqual(read_json(run/'status.json')['state'], 'paused')
        atomic_json(run/'control.json', {'command': 'run'}); train_state.train(self.config, run, 'cpu', 4, factory)
        atomic_json(run/'control.json', {'command': 'stop'}); train_state.train(self.config, run, 'cpu', 8, factory)
        self.assertEqual(self.payload(run)['step'], 4); self.assertEqual(read_json(run/'status.json')['state'], 'stopped')
        with self.assertRaisesRegex(ValueError, 'changed'):
            train_state.train({**self.config, 'encoder_learning_rate': .0001}, run, 'cpu', 8, factory)


if __name__ == '__main__': unittest.main()
