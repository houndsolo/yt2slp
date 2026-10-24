from copy import deepcopy
from itertools import product
import unittest

from yt2slp.button_decoder import BUTTONS, HEADS, _path, button_consistency, constrain_buttons


def predictions(sequence, ports=(1, 0)):
    rows = []
    for i, scores in enumerate(sequence):
        for port in ports:
            logits = [[-8.]*len(BUTTONS) for _ in HEADS]
            for head in range(3): logits[head][list(BUTTONS).index('a')] = scores[head]
            masks = {head: sum(bit for bit, value in zip(BUTTONS.values(), logits[h]) if value >= 0)
                     for h, head in enumerate(HEADS)}
            rows.append({'frame': i+101, 'video_frame': i+15, 'port': port, 'character': 2,
                'button_logits': logits, 'buttons': masks, 'axes': {'stick_x': -.7}, 'axis_bins': {'stick_x': 2},
                'action': 24, 'airborne': False})
    return {'kind': 'frozen-image-controller-predictions', 'slot_ports': list(ports),
        'prediction_interval': [101, 100+len(sequence)], 'checkpoint_sha256': 'frozen', 'rows': rows}


class ButtonDecoderTests(unittest.TestCase):
    def test_press_hold_release_and_simultaneous_buttons(self):
        raw = predictions([(8, 8, -8), (8, -8, -8), (-8, -8, 8)])
        # Both physical ports can press A at the same time; no slot remapping.
        before = deepcopy(raw); decoded = constrain_buttons(raw)
        self.assertEqual(raw, before)
        for port in raw['slot_ports']:
            self.assertEqual([r['buttons'] for r in decoded['rows'] if r['port'] == port],
                [dict(hold=256, press=256, release=0), dict(hold=256, press=0, release=0),
                 dict(hold=0, press=0, release=256)])
        self.assertEqual(button_consistency(decoded)['invalid_button_frames'], 0)
        for original, row in zip(raw['rows'], decoded['rows']):
            self.assertEqual({k: v for k, v in original.items() if k != 'buttons'},
                             {k: v for k, v in row.items() if k != 'buttons'})

    def test_one_frame_tap_and_no_forced_terminal_release(self):
        decoded = constrain_buttons(predictions([(9, 9, -9), (-9, -9, 9), (9, 9, -9)]))
        rows = [r['buttons'] for r in decoded['rows'] if r['port'] == 0]
        self.assertEqual(rows, [dict(hold=256, press=256, release=0), dict(hold=0, press=0, release=256),
                               dict(hold=256, press=256, release=0)])

    def test_initial_state_is_inferred_including_release_on_first_frame(self):
        for scores, initial, expected in (((9, -9, -9), 256, dict(hold=256, press=0, release=0)),
                                         ((-9, -9, 9), 256, dict(hold=0, press=0, release=256))):
            decoded = constrain_buttons(predictions([scores], ports=(3,)))
            self.assertEqual(decoded['button_decoder']['initial_held'], {'3': initial})
            self.assertEqual(decoded['rows'][0]['buttons'], expected)
            self.assertEqual(button_consistency(decoded)['invalid_button_frames'], 0)

    def test_impossible_raw_edges_are_repaired_across_whole_sequence(self):
        raw = predictions([(-2, 5, 7), (2, 5, 7), (2, 5, 7), (-2, 5, 7)])
        self.assertGreater(button_consistency(raw)['invalid_button_frames'], 0)
        decoded = constrain_buttons(raw)
        self.assertEqual(button_consistency(decoded)['invalid_button_frames'], 0)
        self.assertGreater(sum(decoded['button_decoder']['changed_button_frames'].values()), 0)

    def test_global_path_matches_exhaustive_search_and_can_use_future_evidence(self):
        cases = [[(-1, 4, -2), (-1, -2, 8)], [(0, 0, 0)]*4,
                 [(-2, 3, 1), (4, -3, 2), (-5, 2, 6), (1, 4, -3)]]
        def score(initial, path, logits):
            total = 0; previous = initial
            for held, (h, p, r) in zip(path, logits):
                total += held*h + int(not previous and held)*p + int(previous and not held)*r
                previous = held
            return total
        for logits in cases:
            initial, path = _path(logits)
            best = max(score(states[0], states[1:], logits) for states in product((0, 1), repeat=len(logits)+1))
            self.assertEqual(score(initial, path, logits), best)
        # At the first frame, pressing scores 3 > staying released at 0.
        # The following strong press makes staying released then pressing better.
        self.assertEqual(_path([(-1, 4, -2), (2, 20, -5)]), (0, [0, 1]))
        self.assertEqual(_path([(0, 0, 0)]*3), (0, [0, 0, 0]))

    def test_multiple_buttons_are_independent_and_can_overlap(self):
        raw = predictions([(8, 8, -8), (8, -8, -8)])
        x = list(BUTTONS).index('x')
        for row in raw['rows']:
            for h, value in enumerate((8, 8 if row['frame'] == 101 else -8, -8)):
                row['button_logits'][h][x] = value
        decoded = constrain_buttons(raw)
        self.assertEqual(decoded['rows'][0]['buttons']['press'], 256 | 1024)
        self.assertEqual(decoded['rows'][-1]['buttons']['hold'], 256 | 1024)

    def test_rejects_missing_duplicate_or_gapped_frames_and_ports(self):
        raw = predictions([(1, 1, -1), (-1, -1, 1)])
        malformed = []
        case = deepcopy(raw); case['rows'].pop(); malformed.append(case)
        case = deepcopy(raw); case['rows'][1] = deepcopy(case['rows'][0]); malformed.append(case)
        case = deepcopy(raw); case['rows'][-1]['frame'] += 1; malformed.append(case)
        case = deepcopy(raw); case['slot_ports'] = [1, 1]; malformed.append(case)
        for case in malformed:
            with self.assertRaises(ValueError): constrain_buttons(case)

    def test_rejects_nonfinite_logits_wrong_vocabulary_and_redecoding(self):
        for value in (float('inf'), float('nan'), True):
            case = predictions([(1, 1, -1)]); case['rows'][0]['button_logits'][0][0] = value
            with self.assertRaises(ValueError): constrain_buttons(case)
        case = predictions([(1, 1, -1)]); case['rows'][0]['button_logits'][1].pop()
        with self.assertRaises(ValueError): constrain_buttons(case)
        case = predictions([(1, 1, -1)]); case['rows'][0]['buttons']['hold'] |= 128
        with self.assertRaises(ValueError): constrain_buttons(case)
        with self.assertRaises(ValueError): constrain_buttons(constrain_buttons(predictions([(1, 1, -1)])))


if __name__ == '__main__': unittest.main()
