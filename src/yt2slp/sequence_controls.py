"""Hard controller constraints for the held-state sequence model."""
from copy import deepcopy
import math

from .button_decoder import button_consistency
from .prediction_scoring import AXES, BUTTONS

METHOD = 'held-state-difference-v1'
Z_TRIGGER = 0.3499999940395355  # NTSC 1.02 float32; Z overrides digital L/R.
Z_TRIGGER_BIN = 6


def trigger_rule(buttons):
    if buttons & BUTTONS['z']: return Z_TRIGGER, Z_TRIGGER_BIN
    if buttons & (BUTTONS['l'] | BUTTONS['r']): return 1., 16
    return None


def decode_sequence(proposals):
    """Use the first image prediction as a seed; emit subsequent transitions.

The seed is a preceding, fully contextualized image-center prediction, never a
replay answer. Every emitted row has an explicit previous held state. There are
no independent edge heads, Viterbi weights or label-dependent thresholds.
    """
    if proposals.get('kind') != 'frozen-image-held-state-proposals':
        raise ValueError('original held-state proposals required')
    ports = proposals['slot_ports']; first, last = proposals['prediction_interval']
    if (any(type(p) is not int or not 0 <= p <= 3 for p in ports) or not ports
            or len(set(ports)) != len(ports) or type(first) is not int or type(last) is not int
            or last <= first or len(proposals['rows']) != (last-first+1)*len(ports)):
        raise ValueError('complete contiguous image predictions including a seed frame required')
    keyed = {}
    for row in proposals['rows']:
        frame, port = row['frame'], row['port']; logits = row['held_logits']
        if (type(frame) is not int or type(port) is not int or not first <= frame <= last
                or port not in ports or (frame, port) in keyed):
            raise ValueError('missing/duplicate player-frame proposal')
        if len(logits) != len(BUTTONS) or any(type(v) not in (int, float) or not math.isfinite(v) for v in logits):
            raise ValueError('finite held logits in the declared button vocabulary required')
        if set(row['axis_bins']) != set(AXES) or any(type(v) is not int or not 0 <= v <= 16 for v in row['axis_bins'].values()):
            raise ValueError('declared conditional axis bins required')
        keyed[frame, port] = row
    held = lambda row: sum(bit for bit, value in zip(BUTTONS.values(), row['held_logits']) if value >= 0)
    result = deepcopy(proposals); result['kind'] = 'frozen-image-controller-predictions'
    initial = {str(p): held(keyed[first, p]) for p in ports}; rows = []; forced = 0
    for frame in range(first+1, last+1):
        for port in ports:
            row = deepcopy(keyed[frame, port]); previous = held(keyed[frame-1, port]); current = held(row)
            row['buttons'] = {'hold': current, 'press': current & ~previous, 'release': previous & ~current}
            row['conditional_trigger_bin'] = row['axis_bins']['trigger']
            row['axes'] = {name: (0 if name == 'trigger' else -1)+value/16*(1 if name == 'trigger' else 2)
                           for name, value in row['axis_bins'].items()}
            rule = trigger_rule(current)
            if rule:
                row['axes']['trigger'], row['axis_bins']['trigger'] = rule; forced += 1
            rows.append(row)
    result.update(rows=rows, prediction_interval=[first+1, last],
        leading_context_frames=proposals['context_frames']//2+1,
        trailing_context_frames=proposals['context_frames']//2,
        button_decoder={'method': METHOD, 'initial_held': initial,
            'initial_state_policy': 'preceding image-only held-state prediction; no label seed',
            'button_bits': dict(BUTTONS), 'minimum_hold_frames': 1},
        trigger_constraint={'method': 'digital-shoulder-z-priority-v1', 'digital_lr': 1.,
            'z_override': Z_TRIGGER, 'z_bin': Z_TRIGGER_BIN, 'forced_player_frames': forced},
        policy='image-only held states; edges derived from adjacent states; Z overrides L/R trigger; no label seed or optimizer update')
    result['button_decoder']['consistency'] = button_consistency(result)
    return result
