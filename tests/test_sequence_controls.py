from copy import deepcopy
import unittest

from yt2slp.button_decoder import button_consistency
from yt2slp.prediction_scoring import AXES, BUTTONS
from yt2slp.sequence_controls import Z_TRIGGER, decode_sequence


def proposals(masks, ports=(1, 3)):
    rows = []
    for i, mask in enumerate(masks):
        for port in ports:
            rows.append({'frame': 100+i, 'video_frame': 15+i, 'port': port, 'character': 2,
                'held_logits': [5. if mask & bit else -5. for bit in BUTTONS.values()],
                'axis_bins': dict.fromkeys(AXES, 8), 'action': 24, 'airborne': False})
    return {'kind': 'frozen-image-held-state-proposals', 'slot_ports': list(ports), 'context_frames': 31,
        'prediction_interval': [100, 99+len(masks)], 'rows': rows, 'checkpoint_sha256': 'frozen'}


class SequenceControlTests(unittest.TestCase):
    def test_seed_press_hold_release_and_original_proposals_preserved(self):
        raw = proposals([0, 256, 256, 0]); before = deepcopy(raw); decoded = decode_sequence(raw)
        self.assertEqual(raw, before); self.assertEqual(decoded['prediction_interval'], [101, 103])
        self.assertEqual(decoded['leading_context_frames'], 16); self.assertEqual(decoded['trailing_context_frames'], 15)
        self.assertEqual(decoded['button_decoder']['initial_held'], {'1': 0, '3': 0})
        for port in (1, 3):
            self.assertEqual([r['buttons'] for r in decoded['rows'] if r['port'] == port],
                [dict(hold=256, press=256, release=0), dict(hold=256, press=0, release=0), dict(hold=0, press=0, release=256)])
        self.assertEqual(button_consistency(decoded)['invalid_button_frames'], 0)

    def test_shoulder_trigger_and_z_priority_preserve_soft_analog(self):
        decoded = decode_sequence(proposals([0, 64, 32, 16 | 64, 16, 0]))
        rows = [r for r in decoded['rows'] if r['port'] == 1]
        self.assertEqual([r['axes']['trigger'] for r in rows], [1., 1., Z_TRIGGER, Z_TRIGGER, .5])
        self.assertEqual([r['axis_bins']['trigger'] for r in rows], [16, 16, 6, 6, 8])
        self.assertTrue(all(r['axes']['stick_x'] == 0. for r in rows))
        self.assertEqual(decoded['trigger_constraint']['forced_player_frames'], 8)

    def test_one_frame_tap_and_image_seed_held_across_start(self):
        decoded = decode_sequence(proposals([1024, 0, 256 | 1024, 0]))
        rows = [r['buttons'] for r in decoded['rows'] if r['port'] == 1]
        self.assertEqual(rows[0], dict(hold=0, press=0, release=1024))
        self.assertEqual(rows[1], dict(hold=1280, press=1280, release=0))
        self.assertEqual(rows[2], dict(hold=0, press=0, release=1280))

    def test_rejects_missing_duplicate_gapped_or_invalid_proposals(self):
        raw = proposals([0, 256]); cases = []
        case = deepcopy(raw); case['rows'].pop(); cases.append(case)
        case = deepcopy(raw); case['rows'][1] = deepcopy(case['rows'][0]); cases.append(case)
        case = deepcopy(raw); case['rows'][-1]['frame'] += 1; cases.append(case)
        case = deepcopy(raw); case['rows'][0]['held_logits'][0] = float('nan'); cases.append(case)
        case = deepcopy(raw); case['rows'][0]['axis_bins']['trigger'] = 17; cases.append(case)
        for case in cases:
            with self.assertRaises(ValueError): decode_sequence(case)
        with self.assertRaises(ValueError): decode_sequence(decode_sequence(raw))


if __name__ == '__main__': unittest.main()
