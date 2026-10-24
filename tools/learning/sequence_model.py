"""Held-state training: valid edges and digital shoulder coupling by construction."""
import torch
from torch import nn
from torch.nn import functional as F

from baseline import ACTIONS, AXES, BINS, BUTTONS, masked_mean
from yt2slp.sequence_controls import Z_TRIGGER_BIN

L, R, Z = (list(BUTTONS).index(name) for name in ('l', 'r', 'z'))


class SequenceProposal(nn.Module):
    def __init__(self, feature_size=3072, hidden=128):
        super().__init__()
        self.project = nn.Sequential(nn.Linear(feature_size, hidden), nn.ReLU())
        self.temporal = nn.GRU(hidden, hidden, batch_first=True, bidirectional=True)
        self.held_head = nn.Linear(hidden*2, 2*len(BUTTONS))
        self.axes_head = nn.Linear(hidden*2, 2*len(AXES)*BINS)
        self.action_head = nn.Linear(hidden*2, 2*ACTIONS)
        self.air_head = nn.Linear(hidden*2, 2)

    def forward(self, features):
        if features.ndim != 4: raise ValueError('batch/sequence/context/features tensor required')
        batch, steps, context, width = features.shape
        sequence, _ = self.temporal(self.project(features.reshape(batch*steps, context, width)))
        center = sequence[:, context//2]
        return {'held': self.held_head(center).reshape(batch, steps, 2, len(BUTTONS)),
            'axes': self.axes_head(center).reshape(batch, steps, 2, len(AXES), BINS),
            'action': self.action_head(center).reshape(batch, steps, 2, ACTIONS),
            'airborne': self.air_head(center).reshape(batch, steps, 2)}


def hard_controls(prediction):
    held = prediction['held'] >= 0; current, previous = held[:, 1:], held[:, :-1]
    buttons = torch.stack((current, current & ~previous, previous & ~current), dim=-2)
    axes = prediction['axes'][:, 1:].argmax(-1)
    lr = current[..., L] | current[..., R]; z = current[..., Z]
    axes[..., 4] = torch.where(z, Z_TRIGGER_BIN, torch.where(lr, BINS-1, axes[..., 4]))
    return buttons, axes


def proposal_rows(prediction, frames, ports, characters):
    if (prediction['held'].shape[:2] != (1, len(frames)) or len(ports) != 2 or len(characters) != 2
            or not all(torch.isfinite(value).all() for value in prediction.values())):
        raise ValueError('finite image predictions with the exact two physical slots required')
    rows = []
    for i, frame in enumerate(frames):
        for slot, (port, character) in enumerate(zip(ports, characters)):
            rows.append({'frame': frame['replay_frame'], 'video_frame': frame['index'], 'port': port, 'character': character,
                'held_logits': prediction['held'][0, i, slot].tolist(),
                'axis_bins': dict(zip(AXES, prediction['axes'][0, i, slot].argmax(-1).tolist())),
                'action': int(prediction['action'][0, i, slot].argmax()),
                'airborne': bool(prediction['airborne'][0, i, slot] >= 0)})
    return rows


def edge_nll(log_probability, target, weight):
    # Stable log(1-p), including probabilities extremely close to zero or one.
    log_negative = torch.log((-torch.expm1(log_probability)).clamp_min(torch.finfo(log_probability.dtype).tiny))
    return -(weight*target*log_probability+(1-target)*log_negative)


def sequence_loss(prediction, targets, weights):
    if prediction['held'].shape[1] < 2: raise ValueError('preceding seed and current frame required')
    held = targets['buttons'][:, :, :, 0]; held_mask = targets['buttons_mask'][:, :, :, 0]
    both = held_mask[:, 1:] & held_mask[:, :-1]
    current = {k: v[:, 1:] for k, v in targets.items()}
    expected = (held[:, 1:].bool() & ~held[:, :-1].bool(), held[:, :-1].bool() & ~held[:, 1:].bool())
    for head, expected_edges in enumerate(expected, 1):
        if ((current['buttons'][:, :, :, head].bool() != expected_edges) & both & current['buttons_mask'][:, :, :, head]).any():
            raise ValueError('source button edges disagree with contiguous held states')
    logits = prediction['held']; log_held, log_off = F.logsigmoid(logits), F.logsigmoid(-logits)
    losses = [masked_mean(F.binary_cross_entropy_with_logits(logits, held, pos_weight=weights[:, 0], reduction='none'), held_mask)]
    for head, log_event in ((1, log_off[:, :-1]+log_held[:, 1:]), (2, log_held[:, :-1]+log_off[:, 1:])):
        losses.append(masked_mean(edge_nll(log_event, current['buttons'][:, :, :, head], weights[:, head]),
            both & current['buttons_mask'][:, :, :, head]))
    truth = current['buttons'][:, :, :, 0].bool(); known = current['buttons_mask'][:, :, :, 0]
    digital_known = known[..., L] & known[..., R] & known[..., Z]
    z = truth[..., Z]; lr = truth[..., L] | truth[..., R]; forced = digital_known & (z | lr)
    forced_bin = torch.where(z, Z_TRIGGER_BIN, BINS-1)
    if ((current['axes'][..., 4] != forced_bin) & forced & current['axes_mask'][..., 4]).any():
        raise ValueError('original trigger label contradicts digital shoulder/Z rule')
    axis_mask = current['axes_mask'].clone()
    # The conditional trigger head is learned only where digital buttons do not
    # fix its value. Deterministic branches have probability one, hence zero NLL.
    axis_mask[..., 4] &= ~forced
    axes = F.cross_entropy(prediction['axes'][:, 1:].reshape(-1, BINS), current['axes'].reshape(-1), reduction='none').reshape_as(current['axes'])
    action = F.cross_entropy(prediction['action'][:, 1:].reshape(-1, ACTIONS), current['action'].reshape(-1), reduction='none').reshape_as(current['action'])
    air = F.binary_cross_entropy_with_logits(prediction['airborne'][:, 1:], current['airborne'], reduction='none')
    components = {'buttons': sum(losses)/3, 'axes': masked_mean(axes, axis_mask),
        'action': masked_mean(action, current['action_mask']), 'airborne': masked_mean(air, current['airborne_mask'])}
    return sum(components.values()), components


def sequence_metrics(prediction, targets):
    buttons, axes = hard_controls(prediction); targets = {k: v[:, 1:] for k, v in targets.items()}
    result = {'button_metrics': {}, 'state_metrics': {}}
    for head, name in enumerate(('hold', 'press', 'release')):
        actual = targets['buttons'][:, :, :, head].bool(); guessed = buttons[:, :, :, head]
        valid = targets['buttons_mask'][:, :, :, head]
        result['button_metrics'][name] = {k: int(v.sum()) for k, v in
            (('tp', guessed & actual & valid), ('fp', guessed & ~actual & valid), ('fn', ~guessed & actual & valid))}
    def accuracy(guessed, actual, valid):
        return {'compared': int(valid.sum()), 'correct': int(((guessed == actual) & valid).sum())}
    for i, name in enumerate(AXES):
        valid = targets['axes_mask'][..., i]; actual = targets['axes'][..., i]
        result['state_metrics']['axis_'+name] = {**accuracy(axes[..., i], actual, valid),
            'neutral_correct': int(((actual == (0 if name == 'trigger' else 8)) & valid).sum())}
    result['state_metrics']['action'] = accuracy(prediction['action'][:, 1:].argmax(-1), targets['action'], targets['action_mask'])
    result['state_metrics']['airborne'] = accuracy(prediction['airborne'][:, 1:] >= 0, targets['airborne'].bool(), targets['airborne_mask'])
    current = buttons[..., 0, :]; pressed = buttons[..., 1, :]; released = buttons[..., 2, :]
    previous = prediction['held'][:, :-1] >= 0
    invalid = (pressed != (current & ~previous)) | (released != (previous & ~current))
    wrong_trigger = ((current[..., L] | current[..., R]) & ~current[..., Z] & (axes[..., 4] != 16))
    wrong_trigger |= current[..., Z] & (axes[..., 4] != Z_TRIGGER_BIN)
    result['constraint_metrics'] = {'invalid_button_frames': int(invalid.sum()), 'invalid_trigger_frames': int(wrong_trigger.sum())}
    return result
