"""Matched visual-state branches with supplied player identity and attention."""
from copy import deepcopy

from train_smoke import torch
from torch import nn
from torch.nn import functional as F
from torchvision.models import resnet18

from yt2slp.state_plan import SETUP_SIZE


class StateBranch(nn.Module):
    def __init__(self, last_block, channels=512, hidden=128):
        super().__init__(); self.last = last_block
        self.keys = nn.Conv2d(channels, 64, 1); self.values = nn.Conv2d(channels, hidden, 1)
        self.query = nn.Linear(SETUP_SIZE, 64); self.position = nn.Linear(2, 64, bias=False)
        self.global_view = nn.Linear(channels, hidden); self.identity = nn.Linear(SETUP_SIZE, hidden)
        self.head = nn.Sequential(nn.Linear(hidden*3, hidden), nn.ReLU())
        self.action = nn.Linear(hidden, 512); self.airborne = nn.Linear(hidden, 1)

    def train(self, mode=True):
        super().train(mode)
        # Both branches keep identical ImageNet BN statistics. Convolution
        # gradients in the fine-tuned last block remain enabled in eval mode.
        self.last.eval(); return self

    def forward(self, features, setup):
        spatial = self.last(features); batch, _, height, width = spatial.shape
        yy, xx = torch.meshgrid(torch.linspace(-1, 1, height, device=spatial.device),
                               torch.linspace(-1, 1, width, device=spatial.device), indexing='ij')
        positions = self.position(torch.stack((xx.flatten(), yy.flatten()), -1))
        keys = self.keys(spatial).flatten(2).transpose(1, 2)+positions
        query = self.query(setup); attention = (torch.bmm(query, keys.transpose(1, 2))/8).softmax(-1)
        local = torch.bmm(attention, self.values(spatial).flatten(2).transpose(1, 2))
        global_view = self.global_view(spatial.mean((-1, -2))).unsqueeze(1).expand(-1, 2, -1)
        hidden = self.head(torch.cat((local, global_view, self.identity(setup)), -1))
        return {'action': self.action(hidden), 'airborne': self.airborne(hidden).squeeze(-1),
                'attention': attention.reshape(batch, 2, height, width)}


def make_models(weights_path):
    encoder = resnet18(weights=None)
    encoder.load_state_dict(torch.load(weights_path, map_location='cpu', weights_only=True), strict=True)
    prefix = nn.Sequential(encoder.conv1, encoder.bn1, encoder.relu, encoder.maxpool,
                           encoder.layer1, encoder.layer2, encoder.layer3).eval().requires_grad_(False)
    frozen = StateBranch(deepcopy(encoder.layer4).eval().requires_grad_(False))
    finetuned = deepcopy(frozen); finetuned.last.requires_grad_(True)
    return prefix, {'frozen': frozen, 'finetuned': finetuned}


def normalize(images, device):
    images = images.to(device, dtype=torch.float32)/255
    mean = images.new_tensor((.485, .456, .406))[None, :, None, None]
    std = images.new_tensor((.229, .224, .225))[None, :, None, None]
    return (images-mean)/std


def state_loss(prediction, targets):
    def masked(values, mask): return (values*mask).sum()/mask.sum().clamp_min(1)
    action = F.cross_entropy(prediction['action'].reshape(-1, 512), targets['action'].reshape(-1), reduction='none').reshape_as(targets['action'])
    air = F.binary_cross_entropy_with_logits(prediction['airborne'], targets['airborne'], reduction='none')
    return masked(action, targets['action_mask'])+masked(air, targets['airborne_mask'])


def state_counts(prediction, targets):
    valid = targets['action_mask']; actual = targets['action']; guessed = prediction['action'].argmax(-1)
    total = torch.bincount(actual[valid], minlength=512)
    correct = torch.bincount(actual[valid & (actual == guessed)], minlength=512)
    air = targets['airborne'].bool(); predicted_air = prediction['airborne'] >= 0; air_mask = targets['airborne_mask']
    return {'action_total': total.cpu(), 'action_correct': correct.cpu(),
        'air': torch.tensor([int((air_mask & air & predicted_air).sum()), int((air_mask & ~air & ~predicted_air).sum()),
                             int((air_mask & ~air & predicted_air).sum()), int((air_mask & air & ~predicted_air).sum())])}


def summarize_counts(counts):
    total, correct = counts['action_total'], counts['action_correct']; present = total > 0
    tp, tn, fp, fn = counts['air'].tolist()
    return {'action_accuracy': float(correct.sum()/total.sum().clamp_min(1)),
        'action_macro_recall': float((correct[present]/total[present]).mean()) if present.any() else None,
        'action_classes': int(present.sum()), 'player_frames': int(total.sum()),
        'airborne_accuracy': (tp+tn)/max(tp+tn+fp+fn, 1),
        'airborne_balanced_accuracy': ((tp/(tp+fn) if tp+fn else 0)+(tn/(tn+fp) if tn+fp else 0))/2,
        'airborne_counts': dict(tp=tp, tn=tn, fp=fp, fn=fn)}
