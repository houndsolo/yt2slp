"""Train a small temporal head on a training clip; no held-out accuracy claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import tempfile

# The development container runs with the host UID, which has no passwd entry.
# torchvision imports Dynamo even for eager CPU execution; avoid its username-
# derived default cache path without changing the container's user environment.
os.environ.setdefault('TORCHINDUCTOR_CACHE_DIR', str(Path(tempfile.gettempdir())/f'yt2slp-inductor-{os.getuid()}'))

from PIL import Image, ImageOps
import torch
from torch import nn
import torchvision
from torchvision.models import resnet18, ResNet18_Weights
from torchvision.transforms import functional as TF

from baseline import AXES, BINS, BUTTONS, TemporalProposal, binary_metrics, proposal_loss, targets_for_frames


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def encode_images(pairs_path, pairs, batch_size):
    # Retain the entire frame, including off-center fighters; no central crop.
    # Coarse spatial pooling retains more location evidence than one global vector.
    encoder = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    encoder = nn.Sequential(*list(encoder.children())[:-2], nn.AdaptiveAvgPool2d((2, 3)), nn.Flatten()).eval()
    features = []
    with torch.inference_mode():
        for start in range(0, len(pairs['frames']), batch_size):
            images = []
            for frame in pairs['frames'][start:start+batch_size]:
                image_path = pairs_path.parent/frame['image']
                if digest(image_path) != frame['image_sha256']:
                    raise ValueError('image changed after pairing')
                with Image.open(image_path) as image:
                    image = ImageOps.pad(image.convert('RGB'), (384, 320), method=Image.Resampling.BILINEAR)
                    tensor = TF.to_tensor(image)
                images.append(TF.normalize(tensor, [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]))
            features.append(encoder(torch.stack(images)))
            print(f"encoded {min(start+batch_size, len(pairs['frames']))}/{len(pairs['frames'])}", flush=True)
    return torch.cat(features).clone()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=100)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.steps <= 10000 or not 1 <= args.batch_size <= 64 or not 1 <= args.threads <= 32:
        parser.error('invalid bounded smoke-test settings')
    pairs = json.loads(args.pairs.read_text())
    if (pairs.get('kind') != 'supervised-video-replay-pairs' or pairs.get('split') != 'train'
            or sorted(p['character'] for p in pairs['settings']['players']) != [2, 20]
            or pairs['settings']['stage'] != 31):
        parser.error('smoke test requires a declared Fox/Falco Battlefield training clip')
    args.output.mkdir(parents=True, exist_ok=False)
    random.seed(args.seed); torch.manual_seed(args.seed); torch.set_num_threads(args.threads)
    features = encode_images(args.pairs, pairs, args.batch_size)
    torch.save({'pairs_sha256': digest(args.pairs), 'features': features}, args.output/'features.pt')
    centers = torch.tensor(pairs['window_centers'])
    half = pairs['context_frames']//2
    offsets = torch.arange(-half, half+1)
    inputs = features[centers[:, None]+offsets]
    targets = {k: v[centers] for k, v in targets_for_frames(pairs['frames']).items()}
    model = TemporalProposal(feature_size=features.shape[1])
    # Derived only from this training clip; never from validation/test labels.
    positive = (targets['buttons']*targets['buttons_mask']).sum(0)
    negative = ((1-targets['buttons'])*targets['buttons_mask']).sum(0)
    weights = (negative/positive.clamp(min=1)).clamp(min=1, max=20)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001)
    model.eval()
    with torch.no_grad():
        initial, _ = proposal_loss(model(inputs), targets, weights)
    history = []
    model.train()
    for step in range(args.steps):
        chosen = torch.randint(len(centers), (min(args.batch_size, len(centers)),))
        optimizer.zero_grad()
        loss, _ = proposal_loss(model(inputs[chosen]), {k: v[chosen] for k, v in targets.items()}, weights)
        if not torch.isfinite(loss):
            raise ValueError('non-finite training loss')
        loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 5); optimizer.step()
        if step % 10 == 0 or step+1 == args.steps:
            history.append({'step': step+1, 'minibatch_loss': float(loss.detach())})
            print(history[-1], flush=True)
    model.eval()
    with torch.no_grad():
        predictions = model(inputs)
        final, components = proposal_loss(predictions, targets, weights)
    torch.save({'model': model.state_dict(), 'pairs_sha256': digest(args.pairs),
        'buttons': BUTTONS, 'axes': AXES, 'axis_bins': BINS, 'context': pairs['context_frames']}, args.output/'model.pt')
    result = {'schema': 1, 'kind': 'training-clip-smoke-test', 'device': 'cpu',
        'torch_version': torch.__version__, 'seed': args.seed, 'steps': args.steps,
        'torchvision_version': torchvision.__version__,
        'encoder_weights_sha256': digest(Path(torch.hub.get_dir())/'checkpoints/resnet18-f37072fd.pth'),
        'frames': len(features), 'train_windows': len(centers), 'context_frames': pairs['context_frames'],
        'encoder': 'frozen ResNet18 IMAGENET1K_V1; whole-frame 384x320 letterbox; spatial 2x3 pooling',
        'temporal_model': 'bidirectional GRU, hidden 128; image features only',
        'trainable_parameters': sum(p.numel() for p in model.parameters()),
        'pairs_sha256': digest(args.pairs), 'script_sha256': digest(Path(__file__)),
        'baseline_sha256': digest(Path(__file__).with_name('baseline.py')),
        'initial_training_loss': float(initial), 'final_training_loss': float(final),
        'final_loss_components': {k: float(v) for k, v in components.items()},
        'training_button_metrics': binary_metrics(predictions, targets), 'history': history,
        'image_post_phase_verified': pairs['timing']['image_post_phase_verified'],
        'native_vi_adapter_verified': False, 'held_out_evaluation': False,
        'generated_replay_validated': False, 'generalization_established': False,
        'passed': bool(torch.isfinite(final) and final < initial),
        'policy': 'optimizer/data-path smoke test on previously examined training clip; provisional phase; no reconstruction or accuracy acceptance'}
    (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
