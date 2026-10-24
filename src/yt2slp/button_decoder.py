"""Label-free, exact button bookkeeping over contiguous prediction sequences.

Each physical button has two states: released and held. All three existing
heads contribute equally to a Viterbi path score. This is an uncalibrated model
score, not a probability of recovering the original controller sequence.
"""
from copy import deepcopy
import math

from .prediction_scoring import BUTTONS

HEADS = ('hold', 'press', 'release')
METHOD = 'two-state-viterbi-v1'
KNOWN_BITS = sum(BUTTONS.values())


def _sequences(prediction):
    if prediction.get('kind') != 'frozen-image-controller-predictions':
        raise ValueError('frozen controller predictions required')
    ports = prediction['slot_ports']; first, last = prediction['prediction_interval']
    if (not ports or any(type(p) is not int or not 0 <= p <= 3 for p in ports)
            or len(set(ports)) != len(ports) or type(first) is not int
            or type(last) is not int or first > last
            or len(prediction['rows']) != (last-first+1)*len(ports)):
        raise ValueError('contiguous complete prediction interval and distinct physical ports required')
    keyed = {}
    for row in prediction['rows']:
        frame, port = row['frame'], row['port']
        if (type(frame) is not int or type(port) is not int or not first <= frame <= last
                or port not in ports or (frame, port) in keyed):
            raise ValueError('missing, duplicate or noncontiguous player-frame key')
        if set(row['buttons']) != set(HEADS) or any(
                type(bits) is not int or bits < 0 or bits & ~KNOWN_BITS for bits in row['buttons'].values()):
            raise ValueError('invalid physical button vocabulary')
        keyed[frame, port] = row
    return {port: [keyed[frame, port] for frame in range(first, last+1)] for port in ports}


def button_consistency(prediction):
    """Count impossible button/frames, allowing an unknown pre-clip state.

For raw predictions the first frame is checked only for internal contradictions;
later frames must match the preceding held mask. Decoded paths also declare
their inferred initial held masks, so their first transitions are checked fully.
"""
    sequences = _sequences(prediction)
    initial = prediction.get('button_decoder', {}).get('initial_held', {})
    invalid_buttons = invalid_rows = total = 0
    for port, rows in sequences.items():
        previous = initial.get(str(port))
        if previous is not None and (type(previous) is not int or previous < 0 or previous & ~KNOWN_BITS):
            raise ValueError('invalid inferred initial button state')
        for row in rows:
            held, pressed, released = (row['buttons'][head] for head in HEADS)
            invalid = (pressed & ~held) | (released & held)
            if previous is not None:
                invalid |= pressed ^ (held & ~previous)
                invalid |= released ^ (previous & ~held)
            invalid_buttons += invalid.bit_count(); invalid_rows += bool(invalid)
            total += len(BUTTONS); previous = held
    return {'button_frames': total, 'invalid_button_frames': invalid_buttons,
        'invalid_player_frames': invalid_rows,
        'first_frame_policy': 'inferred initial held mask' if initial else 'both initial states allowed'}


def _path(logits):
    # log Bernoulli(y; sigmoid(logit)) = y*logit - softplus(logit).
    # The softplus terms are identical for every path and can be omitted.
    # Equal starting scores retain both initial hypotheses; no terminal release
    # or minimum duration is imposed. Ties consistently prefer state zero.
    scores = [0., 0.]; trace = []
    for held_logit, press_logit, release_logit in logits:
        current = []; back = []
        for held in (0, 1):
            candidates = [scores[previous] + held*held_logit
                + int(not previous and held)*press_logit
                + int(previous and not held)*release_logit for previous in (0, 1)]
            previous = max((0, 1), key=lambda state: candidates[state])
            current.append(candidates[previous]); back.append(previous)
        if not all(math.isfinite(score) for score in current):
            raise ValueError('button sequence score overflow')
        scores = current; trace.append(back)
    held = max((0, 1), key=lambda state: scores[state]); path = []
    for back in reversed(trace):
        path.append(held); held = back[held]
    return held, list(reversed(path))


def constrain_buttons(prediction):
    """Return a new artifact; preserve raw logits, axes, frame keys and identity.

No labels, simulator state, tuned durations, thresholds or fitted phase enter
this function. Each port/button path is solved independently across the entire
clip, rather than resetting at model-inference batch boundaries.
    """
    if prediction.get('button_decoder'):
        raise ValueError('decode the original raw predictions, not an already decoded artifact')
    sequences = _sequences(prediction)
    for rows in sequences.values():
        for row in rows:
            logits = row['button_logits']
            if (len(logits) != 3 or any(len(head) != len(BUTTONS) for head in logits)
                    or any(type(value) not in (int, float) or not math.isfinite(value)
                           for head in logits for value in head)):
                raise ValueError('finite hold/press/release logits in the declared vocabulary required')
    result = deepcopy(prediction); decoded = _sequences(result); initial = {}
    changes = dict.fromkeys(HEADS, 0)
    for port, rows in decoded.items():
        masks = [dict.fromkeys(HEADS, 0) for _ in rows]; initial[str(port)] = 0
        for button, bit in enumerate(BUTTONS.values()):
            previous, path = _path([[row['button_logits'][head][button] for head in range(3)] for row in rows])
            if previous: initial[str(port)] |= bit
            for frame, held in enumerate(path):
                if held: masks[frame]['hold'] |= bit
                if held and not previous: masks[frame]['press'] |= bit
                if previous and not held: masks[frame]['release'] |= bit
                previous = held
        for row, mask in zip(rows, masks):
            for head in HEADS: changes[head] += (row['buttons'][head] ^ mask[head]).bit_count()
            row['buttons'] = mask
    result['button_decoder'] = {'method': METHOD, 'head_order': list(HEADS), 'button_bits': dict(BUTTONS),
        'score': 'sum of equally weighted Bernoulli head log-scores; uncalibrated; no fitted priors',
        'initial_state_policy': 'equal scores for both states; infer separately per physical port and button',
        'initial_held': initial, 'terminal_state_policy': 'free', 'minimum_hold_frames': 1,
        'tie_policy': 'prefer released predecessor and released terminal state',
        'changed_button_frames': changes, 'raw_consistency': button_consistency(prediction)}
    result['button_decoder']['decoded_consistency'] = button_consistency(result)
    result['policy'] = ('pixels/known roster; original logits retained; label-free two-state Viterbi buttons; '
        'all three heads weighted equally; unknown initial state; one-frame taps allowed; '
        'axes/action/airborne unchanged; no optimizer update, lag fit or simulator input')
    return result
