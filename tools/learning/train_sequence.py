"""Resumable held-state sequence training with hard controller constraints."""
import argparse
from pathlib import Path
import signal
import time

from train_smoke import torch
import torchvision
from manage import validate_config
from runtime_files import ROOT, atomic_json, digest, read_json, status
from sequence_data import SequenceStore
from sequence_model import SequenceProposal, sequence_loss, sequence_metrics
from train import load_checkpoint, save_checkpoint


def contract(config, dataset, device):
    files = ('train_sequence.py', 'sequence_data.py', 'sequence_model.py', 'baseline.py',
             'train.py', 'corpus_data.py', 'stream_data.py')
    core = ('corpus.py', 'sequence_controls.py', 'button_decoder.py', 'prediction_scoring.py')
    return {'kind': 'held-state-sequence-v1', 'dataset_sha256': digest(dataset),
        'torch_version': str(torch.__version__), 'torchvision_version': str(torchvision.__version__), 'device': device,
        'slot_mapping': 'ascending-physical-ports',
        'code': {**{f: digest(Path(__file__).with_name(f)) for f in files},
                 **{f: digest(ROOT/'src/yt2slp'/f) for f in core}},
        'hyperparameters': {k: config[k] for k in ('context_frames', 'sequence_frames', 'hidden_size', 'batch_size', 'learning_rate', 'seed')},
        'constraints': {'buttons': 'held state plus adjacent differences; no independent edge heads',
            'trigger': 'L/R=1; Z overrides to float32 0.35; otherwise conditional analog head',
            'seed': 'preceding image-center prediction; no replay seed'}}


def infer_clip(network, features, context, device, batch_size):
    """Image features only; each center keeps its own fixed context window."""
    outputs = {}; half = context//2
    with torch.no_grad():
        for start in range(half, len(features)-half, batch_size):
            centers = range(start, min(start+batch_size, len(features)-half))
            windows = torch.stack([features[i-half:i+half+1] for i in centers]).unsqueeze(0).to(device)
            for key, value in network(windows).items(): outputs.setdefault(key, []).append(value.cpu())
    return {k: torch.cat(v, dim=1) for k, v in outputs.items()}


def evaluate(network, store, weights, device, batch_size):
    network.eval(); aggregate = {'button_metrics': {}, 'state_metrics': {}, 'constraint_metrics': {}}
    losses = 0.; frames = 0
    with torch.no_grad():
        for index, shard in enumerate(store.shards):
            payload = store.load(index); half = shard['context_frames']//2
            prediction = infer_clip(network, payload['features'], shard['context_frames'], device, batch_size)
            targets = {k: v[half:shard['frames']-half].unsqueeze(0) for k, v in payload['targets'].items()}
            loss, _ = sequence_loss(prediction, targets, weights.cpu())
            count = shard['windows']-1; losses += float(loss)*count; frames += count
            metrics = sequence_metrics(prediction, targets)
            for group in ('button_metrics', 'state_metrics'):
                for name, counts in metrics[group].items():
                    values = aggregate[group].setdefault(name, {})
                    for key, value in counts.items(): values[key] = values.get(key, 0)+value
            for name, count in metrics['constraint_metrics'].items():
                aggregate['constraint_metrics'][name] = aggregate['constraint_metrics'].get(name, 0)+count
    for metric in aggregate['button_metrics'].values():
        tp, fp, fn = (metric[k] for k in ('tp', 'fp', 'fn'))
        metric.update(f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
                      positive_labels=tp+fn, all_released_baseline_f1=0. if tp+fn else None)
    for metric in aggregate['state_metrics'].values():
        metric['accuracy'] = metric['correct']/metric['compared'] if metric['compared'] else None
        if 'neutral_correct' in metric:
            metric['neutral_baseline_accuracy'] = metric.pop('neutral_correct')/metric['compared'] if metric['compared'] else None
    scores = [m['f1'] for m in aggregate['button_metrics'].values() if m['f1'] is not None]
    aggregate.update(event_f1_mean=sum(scores)/len(scores) if scores else None, loss=losses/max(frames, 1),
        windows=frames, image_seed_frames=len(store.shards),
        policy='full development split; each clip has one image-only seed; exact frame/port; hard button and shoulder/Z constraints')
    network.train(); return aggregate


def train(config, run, device_name='cuda', max_steps=None):
    import json
    validate_config(config); run.mkdir(parents=True, exist_ok=True)
    progress = run/'status.json'; status(progress, 'loading', step=read_json(run/'latest.json', {}).get('step', 0))
    stop = [None]
    def request(signum, frame): stop[0] = 'stop'
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, request)
    torch.set_num_threads(config['threads']); torch.manual_seed(config['seed']); device = torch.device(device_name)
    if device.type == 'cuda':
        if not torch.cuda.is_available(): raise ValueError('CUDA unavailable; no fallback')
        torch.cuda.set_per_process_memory_fraction(config['gpu_memory_fraction']); torch.cuda.manual_seed_all(config['seed'])
    dataset = ROOT/config['data_directory']/'dataset.json'; expected = contract(config, dataset, device_name)
    training = SequenceStore(dataset, 'train', config['sequence_frames'])
    validation = SequenceStore(dataset, 'validation', config['sequence_frames'])
    if training.dataset['context_frames'] != config['context_frames']: raise ValueError('corpus/context mismatch')
    network = SequenceProposal(3072, config['hidden_size']).to(device)
    optimizer = torch.optim.AdamW(network.parameters(), lr=config['learning_rate'])
    weights = training.button_weights().to(device); sampler = torch.Generator().manual_seed(config['seed']+1)
    step = 0; best_score = None; latest_validation = None; latest_loss = None
    restored = load_checkpoint(run, expected)
    if restored:
        network.load_state_dict(restored['model'], strict=True); optimizer.load_state_dict(restored['optimizer'])
        sampler.set_state(restored['sampler_rng']); torch.set_rng_state(restored['torch_rng'])
        if device.type == 'cuda': torch.cuda.set_rng_state_all(restored['cuda_rng'])
        step = restored['step']; best_score = restored['best_score']; latest_validation = restored['validation']
    limit = config['max_steps'] if max_steps is None else max_steps
    if limit < step: raise ValueError('total step limit precedes checkpoint')
    atomic_json(run/'contract.json', expected); started = time.monotonic(); start_step = step
    def checkpoint(best=False):
        return save_checkpoint(run, {'schema': 1, 'kind': 'resumable-held-sequence-trainer', 'step': step, 'contract': expected,
            'model': network.state_dict(), 'optimizer': optimizer.state_dict(), 'sampler_rng': sampler.get_state(),
            'torch_rng': torch.get_rng_state(), 'cuda_rng': torch.cuda.get_rng_state_all() if device.type == 'cuda' else [],
            'best_score': best_score, 'validation': latest_validation}, best)
    def report(state, **more):
        return status(progress, state, step=step, max_steps=limit, train_sequences=training.total,
            sequence_frames=config['sequence_frames'], train_windows=sum(s['windows']-1 for s in training.shards),
            validation_windows=sum(s['windows']-1 for s in validation.shards), training_loss=latest_loss,
            best_validation_event_f1=best_score, latest_validation=latest_validation,
            steps_per_second=(step-start_step)/max(.001, time.monotonic()-started), device=device_name, **more)
    report('running', resumed_from_step=step)
    while True:
        wanted = stop[0] or read_json(run/'control.json', {}).get('command')
        if wanted in ('pause', 'stop'):
            pointer = checkpoint(); report('paused' if wanted == 'pause' else 'stopped', checkpoint=pointer); return
        if step >= limit: checkpoint(); report('completed'); return
        indices = torch.randint(training.total, (config['batch_size'],), generator=sampler).tolist()
        features, targets = training.batch(indices); optimizer.zero_grad(set_to_none=True)
        prediction = network(features.to(device))
        loss, _ = sequence_loss(prediction, {k: v.to(device) for k, v in targets.items()}, weights)
        if not torch.isfinite(loss): raise ValueError('non-finite loss')
        loss.backward(); torch.nn.utils.clip_grad_norm_(network.parameters(), 5); optimizer.step()
        step += 1; latest_loss = float(loss.detach())
        if step % config['evaluate_every'] == 0:
            report('evaluating'); latest_validation = evaluate(network, validation, weights, device, config['batch_size']*(config['sequence_frames']+1))
            score = latest_validation['event_f1_mean']; improved = score is not None and (best_score is None or score > best_score)
            if improved: best_score = score
            pointer = checkpoint(improved)
            with (run/'metrics.ndjson').open('a') as handle:
                handle.write(json.dumps({'step': step, 'validation': latest_validation, 'checkpoint': pointer, 'unix': time.time()})+'\n')
            print(json.dumps({'step': step, 'validation': latest_validation}), flush=True)
        elif step % config['checkpoint_every'] == 0: checkpoint()
        if step % config['log_every'] == 0: print(json.dumps(report('running')), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True); parser.add_argument('--steps', type=int)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cuda'); args = parser.parse_args()
    config = read_json(args.config); run = ROOT/config['run_directory']
    try:
        if args.steps is not None and args.steps < 1: raise ValueError('positive total steps required')
        train(config, run, args.device, args.steps)
    except BaseException as error:
        previous = read_json(run/'status.json', {}); previous.pop('state', None); previous.pop('updated_unix', None); previous.pop('error', None)
        status(run/'status.json', 'failed', **previous, error=str(error)); raise


if __name__ == '__main__': main()
