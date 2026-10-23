"""Frozen, known-roster image inference. This CLI has no target/label argument."""
import argparse
import json
from pathlib import Path

from train_smoke import digest, encode_images  # Exact frozen training preprocessing.
import torch
import torchvision

from baseline import AXES, BINS, BUTTONS, TemporalProposal
from yt2slp.model_contract import slot_ports, validate_image_view


def decode_batch(prediction, frames, ports, characters):
    """Keep trained semantic slots distinct from supplied physical ports."""
    if not all(torch.isfinite(value).all() for value in prediction.values()):
        raise ValueError('non-finite model output')
    rows = []
    for i, frame in enumerate(frames):
        for slot, (port, character) in enumerate(zip(ports, characters)):
            logits = prediction['buttons'][i, slot].tolist()
            bits = [sum(bit for bit, score in zip(BUTTONS.values(), head) if score >= 0) for head in logits]
            axes = prediction['axes'][i, slot].argmax(-1).tolist()
            rows.append({'frame': frame['replay_frame'], 'video_frame': frame['index'],
                'port': port, 'character': character, 'button_logits': logits,
                'buttons': dict(zip(('hold', 'press', 'release'), bits)),
                'axis_bins': dict(zip(AXES, axes)),
                'axes': {name: (0 if name == 'trigger' else -1)+index/(BINS-1)*(1 if name == 'trigger' else 2)
                         for name, index in zip(AXES, axes)},
                'action': int(prediction['action'][i, slot].argmax()),
                'airborne': bool(prediction['airborne'][i, slot] >= 0)})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('model', 'view', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--training-regression', action='store_true', help='explicitly allow the already examined training replay')
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 64: parser.error('batch size must be 1..64')
    torch.set_num_threads(4)
    device = torch.device(args.device)
    if device.type == 'cuda':
        if not torch.cuda.is_available(): parser.error('CUDA requested but unavailable; no fallback')
        torch.cuda.set_per_process_memory_fraction(.5)
    model = json.loads(args.model.read_text()); view = json.loads(args.view.read_text())
    if (model.get('schema') != 1 or model.get('kind') != 'frozen-temporal-image-model'
            or model['button_logit_threshold'] != 0
            or model['baseline_sha256'] != digest(Path(__file__).with_name('baseline.py'))
            or model['training_script_sha256'] != digest(Path(__file__).with_name('train_smoke.py'))
            or model['torch_version'] != torch.__version__ or model['torchvision_version'] != torchvision.__version__):
        raise ValueError('frozen architecture/preprocessing/runtime identity mismatch')
    same_replay = model['training_replay_sha256'] == view['replay_sha256']
    if same_replay and not args.training_regression:
        parser.error('training replay requires explicit --training-regression')
    validate_image_view(view, model['context_frames'])
    ports = slot_ports(model, view['settings'])
    checkpoint = (args.model.parent/model['checkpoint']).resolve()
    if digest(checkpoint) != model['checkpoint_sha256']: raise ValueError('checkpoint changed')
    payload = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if (payload['pairs_sha256'] != model['training_pairs_sha256'] or payload['buttons'] != BUTTONS
            or tuple(payload['axes']) != AXES or payload['axis_bins'] != BINS or payload['context'] != model['context_frames']):
        raise ValueError('checkpoint training identity, vocabulary or context mismatch')
    network = TemporalProposal(model['feature_size'], model['hidden_size']).to(device)
    network.load_state_dict(payload['model'], strict=True); network.eval()
    encoder_weights = Path(torch.hub.get_dir())/'checkpoints/resnet18-f37072fd.pth'
    if not encoder_weights.is_file() or digest(encoder_weights) != model['encoder_weights_sha256']:
        raise ValueError('install exact frozen encoder weights before inference')
    features = encode_images(args.view, view, args.batch_size, device)
    half = model['context_frames']//2; centers = list(range(half, len(features)-half)); rows = []
    with torch.no_grad():
        for start in range(0, len(centers), args.batch_size):
            batch = centers[start:start+args.batch_size]
            windows = torch.stack([features[i-half:i+half+1] for i in batch]).to(device)
            prediction = {k: v.cpu() for k, v in network(windows).items()}
            rows.extend(decode_batch(prediction, [view['frames'][i] for i in batch], ports, model['slot_characters']))
    result = {'schema': 1, 'kind': 'frozen-image-controller-predictions',
        'replay_sha256': view['replay_sha256'], 'view_sha256': digest(args.view),
        'model_descriptor_sha256': digest(args.model), 'checkpoint_sha256': digest(checkpoint),
        'training_replay_sha256': model['training_replay_sha256'], 'training_regression': same_replay,
        'settings': view['settings'], 'slot_ports': ports, 'slot_characters': model['slot_characters'],
        'context_frames': model['context_frames'], 'context_only_edge_frames': half,
        'prediction_interval': [rows[0]['frame'], rows[-1]['frame']], 'rows': rows,
        'policy': 'pixels only; supplied stage/roster map output slots; no target file or optimizer; zero-logit button threshold; independent hold/edge heads, uncalibrated scores',
        'native_vi_adapter_verified': False, 'generated_replay_validated': False}
    with args.output.open('x') as handle: handle.write(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(f"{len(rows)} player-frame predictions; slots -> physical ports {ports}")


if __name__ == '__main__': main()
