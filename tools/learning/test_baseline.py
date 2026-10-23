"""Optional CPU tensor tests; run with the separate learning environment."""
from copy import deepcopy
import unittest

import torch

from baseline import AXES, BINS, BUTTONS, TemporalProposal, binary_metrics, proposal_loss, targets_for_frames
from train_smoke import evaluate


def target_frame():
    row = {'physical': {'values': {'buttons': 1024}, 'mask': {'buttons': True}},
        'physical_edges': {'pressed': 1024, 'released': 512, 'mask': True},
        'effective': {'values': dict(zip(AXES, (-1, 0, 1, 0, 1))), 'mask': dict.fromkeys(AXES, True)},
        'state': {'values': {'action': 24, 'airborne': False}, 'mask': {'action': True, 'airborne': True}}}
    return {'targets': [row, deepcopy(row)]}


class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_target_projection_preserves_press_release_and_axis_endpoints(self):
        target = targets_for_frames([target_frame()])
        self.assertEqual(target['axes'][0, 0].tolist(), [0, 8, 16, 8, 16])
        names = list(BUTTONS)
        self.assertEqual(target['buttons'][0, 0, :, names.index('x')].tolist(), [1, 1, 0])
        self.assertEqual(target['buttons'][0, 0, :, names.index('b')].tolist(), [0, 0, 1])
        self.assertEqual(int(target['action'][0, 1]), 24)
        self.assertEqual(float(target['airborne'][0, 1]), 0)

    def test_missing_control_values_remain_unsupervised(self):
        frame = target_frame()
        for row in frame['targets']:
            row['physical'] = {'values': {'buttons': None}, 'mask': {'buttons': False}}
            row['physical_edges'] = {'pressed': None, 'released': None, 'mask': False}
            row['effective']['values']['stick_y'] = None
            row['effective']['mask']['stick_y'] = False
        target = targets_for_frames([frame])
        self.assertFalse(target['buttons_mask'].any())
        self.assertFalse(target['axes_mask'][0, :, 1].any())

    def test_temporal_output_shapes_and_all_heads_receive_gradients(self):
        model = TemporalProposal(feature_size=8, hidden=8)
        prediction = model(torch.randn(2, 5, 8))
        self.assertEqual(prediction['buttons'].shape, (2, 2, 3, len(BUTTONS)))
        self.assertEqual(prediction['axes'].shape, (2, 2, len(AXES), BINS))
        self.assertEqual(prediction['action'].shape, (2, 2, 512))
        target = targets_for_frames([target_frame(), target_frame()])
        loss, _ = proposal_loss(prediction, target)
        loss.backward()
        for head in (model.project[0], model.temporal, model.button_heads, model.axes_head, model.action_head, model.air_head):
            self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in head.parameters()))

    def test_fully_masked_targets_contribute_zero_loss(self):
        model = TemporalProposal(feature_size=8, hidden=8)
        target = targets_for_frames([target_frame()])
        for key in target:
            if key.endswith('_mask'):
                target[key].zero_()
        loss, _ = proposal_loss(model(torch.zeros(1, 3, 8)), target)
        self.assertEqual(float(loss.detach()), 0)
        loss.backward()

    def test_neutral_predictions_do_not_get_perfect_event_scores(self):
        target = targets_for_frames([target_frame()])
        metrics = binary_metrics({'buttons': torch.full_like(target['buttons'], -100)}, target)
        for head in ('hold', 'press', 'release'):
            self.assertEqual(metrics[head]['f1'], 0)
            self.assertGreater(metrics[head]['fn'], 0)

    def test_batched_evaluation_preserves_predictions_and_masked_loss(self):
        torch.manual_seed(1)
        model = TemporalProposal(feature_size=8, hidden=8)
        inputs = torch.randn(3, 5, 8)
        targets = targets_for_frames([target_frame() for _ in range(3)])
        weights = torch.ones(2, 3, len(BUTTONS))
        complete, complete_loss, _ = evaluate(model, inputs, targets, weights, torch.device('cpu'), 3)
        batched, batched_loss, _ = evaluate(model, inputs, targets, weights, torch.device('cpu'), 1)
        for key in complete:
            torch.testing.assert_close(batched[key], complete[key], rtol=1e-5, atol=1e-6)
            self.assertEqual(batched[key].device.type, 'cpu')
        torch.testing.assert_close(batched_loss, complete_loss)


if __name__ == '__main__':
    unittest.main()
