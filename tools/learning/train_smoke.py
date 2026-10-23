"""Train a small temporal head on a training clip; no held-out accuracy claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import time

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


def encode_images(pairs_path, pairs, batch_size, device):
    # Retain the entire frame, including off-center fighters; no central crop.
    # Coarse spatial pooling retains more location evidence than one global vector.
    encoder = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    encoder = nn.Sequential(*list(encoder.children())[:-2], nn.AdaptiveAvgPool2d((2, 3)), nn.Flatten()).to(device).eval()
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
            features.append(encoder(torch.stack(images).to(device)).cpu())
            print(f"encoded {min(start+batch_size, len(pairs['frames']))}/{len(pairs['frames'])}", flush=True)
    return torch.cat(features).clone()


def evaluate(model, inputs, targets, weights, device, batch_size):
    """Keep complete clip tensors on CPU; bound GPU memory by minibatch size."""
    predictions = {}
    model.eval()
    with torch.no_grad():
        for start in range(0, len(inputs), batch_size):
            for name, value in model(inputs[start:start+batch_size].to(device)).items():
                predictions.setdefault(name, []).append(value.cpu())
    predictions = {k: torch.cat(v) for k, v in predictions.items()}
    loss, components = proposal_loss(predictions, targets, weights.cpu())
    return predictions, loss, components


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=100)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--gpu-memory-fraction', type=float, default=.5)
    args = parser.parse_args()
    if not 1 <= args.steps <= 10000 or not 1 <= args.batch_size <= 64 or not 1 <= args.threads <= 32:
        parser.error('invalid bounded smoke-test settings')
    if not 0 < args.gpu_memory_fraction <= 1:
        parser.error('GPU memory fraction must be in (0, 1]')
    device = torch.device(args.device)
    hardware = {}
    if device.type == 'cuda':
        if not torch.cuda.is_available():
            parser.error('CUDA explicitly requested but unavailable; no CPU fallback')
        torch.cuda.set_per_process_memory_fraction(args.gpu_memory_fraction)
        properties = torch.cuda.get_device_properties(0)
        hardware = {'name': properties.name, 'capability': list(torch.cuda.get_device_capability(0)),
            'total_memory_bytes': properties.total_memory, 'allocator_memory_fraction': args.gpu_memory_fraction,
            'cuda_version': torch.version.cuda, 'cudnn_version': torch.backends.cudnn.version(),
            'compiled_architectures': torch.cuda.get_arch_list()}
    pairs = json.loads(args.pairs.read_text())
    if (pairs.get('kind') != 'supervised-video-replay-pairs' or pairs.get('split') != 'train'
            or sorted(p['character'] for p in pairs['settings']['players']) != [2, 20]
            or pairs['settings']['stage'] != 31):
        parser.error('smoke test requires a declared Fox/Falco Battlefield training clip')
    args.output.mkdir(parents=True, exist_ok=False)
    random.seed(args.seed); torch.manual_seed(args.seed); torch.set_num_threads(args.threads)
    if device.type == 'cuda':
        torch.cuda.manual_seed_all(args.seed)
        torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    features = encode_images(args.pairs, pairs, args.batch_size, device)
    encoding_seconds = time.perf_counter()-started
    torch.save({'pairs_sha256': digest(args.pairs), 'features': features}, args.output/'features.pt')
    centers = torch.tensor(pairs['window_centers'])
    half = pairs['context_frames']//2
    offsets = torch.arange(-half, half+1)
    inputs = features[centers[:, None]+offsets]
    targets = {k: v[centers] for k, v in targets_for_frames(pairs['frames']).items()}
    model = TemporalProposal(feature_size=features.shape[1]).to(device)
    # Derived only from this training clip; never from validation/test labels.
    positive = (targets['buttons']*targets['buttons_mask']).sum(0)
    negative = ((1-targets['buttons'])*targets['buttons_mask']).sum(0)
    weights = (negative/positive.clamp(min=1)).clamp(min=1, max=20).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001)
    _, initial, _ = evaluate(model, inputs, targets, weights, device, args.batch_size)
    history = []
    model.train()
    training_started = time.perf_counter()
    for step in range(args.steps):
        chosen = torch.randint(len(centers), (min(args.batch_size, len(centers)),))
        optimizer.zero_grad()
        loss, _ = proposal_loss(model(inputs[chosen].to(device)),
            {k: v[chosen].to(device) for k, v in targets.items()}, weights)
        if not torch.isfinite(loss):
            raise ValueError('non-finite training loss')
        loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 5); optimizer.step()
        if step % 10 == 0 or step+1 == args.steps:
            history.append({'step': step+1, 'minibatch_loss': float(loss.detach())})
            print(history[-1], flush=True)
    if device.type == 'cuda':
        torch.cuda.synchronize()
    training_seconds = time.perf_counter()-training_started
    predictions, final, components = evaluate(model, inputs, targets, weights, device, args.batch_size)
    torch.save({'model': model.state_dict(), 'pairs_sha256': digest(args.pairs),
        'buttons': BUTTONS, 'axes': AXES, 'axis_bins': BINS, 'context': pairs['context_frames']}, args.output/'model.pt')
    result = {'schema': 1, 'kind': 'training-clip-smoke-test', 'device': str(device), 'hardware': hardware,
        'torch_version': torch.__version__, 'seed': args.seed, 'steps': args.steps,
        'torchvision_version': torchvision.__version__,
        'encoder_weights_sha256': digest(Path(torch.hub.get_dir())/'checkpoints/resnet18-f37072fd.pth'),
        'frames': len(features), 'train_windows': len(centers), 'context_frames': pairs['context_frames'],
        'batch_size': args.batch_size, 'threads': args.threads,
        'encoding_seconds': encoding_seconds, 'training_seconds': training_seconds,
        'training_steps_per_second': args.steps/training_seconds,
        'peak_cuda_allocated_bytes': torch.cuda.max_memory_allocated() if device.type == 'cuda' else None,
        'peak_cuda_reserved_bytes': torch.cuda.max_memory_reserved() if device.type == 'cuda' else None,
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
