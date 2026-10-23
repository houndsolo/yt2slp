"""Optional PyTorch baseline. Inputs are images only; replay fields are targets.

The first executable experiment is explicitly a development-clip smoke test.
It cannot evaluate generalization, recover native PAD timing or emit a replay.
"""
import torch
from torch import nn
from torch.nn import functional as F


BUTTONS = {'dleft': 1, 'dright': 2, 'ddown': 4, 'dup': 8,
           'z': 16, 'r': 32, 'l': 64, 'a': 256, 'b': 512,
           'x': 1024, 'y': 2048, 'start': 4096}
AXES = ('stick_x', 'stick_y', 'cstick_x', 'cstick_y', 'trigger')
BINS = 17
ACTIONS = 512


class TemporalProposal(nn.Module):
    """Spatial image features -> bidirectional GRU -> per-player distributions.

    Known two-player ordering is fixed by the pair manifest's physical ports.
    Axis bins retain alternatives; independent heads do not yet represent joint
    sequence uncertainty or enforce consistency among hold/press/release heads.
    """
    def __init__(self, feature_size=3072, hidden=128):
        super().__init__()
        self.project = nn.Sequential(nn.Linear(feature_size, hidden), nn.ReLU())
        self.temporal = nn.GRU(hidden, hidden, batch_first=True, bidirectional=True)
        self.button_heads = nn.Linear(hidden*2, 2*3*len(BUTTONS))
        self.axes_head = nn.Linear(hidden*2, 2*len(AXES)*BINS)
        self.action_head = nn.Linear(hidden*2, 2*ACTIONS)
        self.air_head = nn.Linear(hidden*2, 2)

    def forward(self, features):
        sequence, _ = self.temporal(self.project(features))
        center = sequence[:, sequence.shape[1]//2]
        return {'buttons': self.button_heads(center).reshape(-1, 2, 3, len(BUTTONS)),
                'axes': self.axes_head(center).reshape(-1, 2, len(AXES), BINS),
                'action': self.action_head(center).reshape(-1, 2, ACTIONS),
                'airborne': self.air_head(center)}


def targets_for_frames(frames):
    n = len(frames)
    result = {name: torch.zeros(shape, dtype=dtype) for name, shape, dtype in (
        ('buttons', (n, 2, 3, len(BUTTONS)), torch.float32),
        ('buttons_mask', (n, 2, 3, len(BUTTONS)), torch.bool),
        ('axes', (n, 2, len(AXES)), torch.long),
        ('axes_mask', (n, 2, len(AXES)), torch.bool),
        ('action', (n, 2), torch.long), ('action_mask', (n, 2), torch.bool),
        ('airborne', (n, 2), torch.float32), ('airborne_mask', (n, 2), torch.bool))}
    for i, frame in enumerate(frames):
        for p, row in enumerate(frame['targets']):
            physical, state, effective = (row[k] for k in ('physical', 'state', 'effective'))
            for h, (value, valid) in enumerate((
                    (physical['values']['buttons'], physical['mask']['buttons']),
                    (row['physical_edges']['pressed'], row['physical_edges']['mask']),
                    (row['physical_edges']['released'], row['physical_edges']['mask']))):
                for b, bit in enumerate(BUTTONS.values()):
                    result['buttons'][i, p, h, b] = bool(value & bit) if valid else False
                    result['buttons_mask'][i, p, h, b] = valid
            for a, name in enumerate(AXES):
                value, valid = effective['values'][name], effective['mask'][name]
                if valid:
                    low = 0 if name == 'trigger' else -1
                    if not low-.001 <= value <= 1.001:
                        raise ValueError('effective axis outside declared normalization')
                    result['axes'][i, p, a] = min(BINS-1, max(0, round((value-low)/(1-low)*(BINS-1))))
                    result['axes_mask'][i, p, a] = True
            for name in ('action', 'airborne'):
                if state['mask'][name]:
                    value = state['values'][name]
                    if name == 'action' and not 0 <= value < ACTIONS:
                        raise ValueError('action outside baseline class vocabulary')
                    result[name][i, p] = value
                    result[name+'_mask'][i, p] = True
    return result


def masked_mean(values, mask):
    # Empty supervision contributes zero and never becomes a negative label.
    return (values*mask).sum()/mask.sum().clamp(min=1)


def proposal_loss(prediction, targets, button_weight=None):
    buttons = F.binary_cross_entropy_with_logits(prediction['buttons'], targets['buttons'],
        pos_weight=button_weight, reduction='none')
    axes = F.cross_entropy(prediction['axes'].reshape(-1, BINS), targets['axes'].reshape(-1),
        reduction='none').reshape_as(targets['axes'])
    action = F.cross_entropy(prediction['action'].reshape(-1, ACTIONS), targets['action'].reshape(-1),
        reduction='none').reshape_as(targets['action'])
    air = F.binary_cross_entropy_with_logits(prediction['airborne'], targets['airborne'], reduction='none')
    components = {name: masked_mean(value, targets[name+'_mask'])
                  for name, value in (('buttons', buttons), ('axes', axes), ('action', action), ('airborne', air))}
    return sum(components.values()), components


def binary_metrics(prediction, targets):
    result = {}
    for h, name in enumerate(('hold', 'press', 'release')):
        actual = targets['buttons'][:, :, h].bool()
        valid = targets['buttons_mask'][:, :, h]
        guessed = prediction['buttons'][:, :, h] >= 0
        tp = int((guessed & actual & valid).sum())
        fp = int((guessed & ~actual & valid).sum())
        fn = int((~guessed & actual & valid).sum())
        result[name] = {'tp': tp, 'fp': fp, 'fn': fn,
            'f1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
            'positive_labels': int((actual & valid).sum())}
    return result
