"""Detached matched frozen/last-block fine-tuned RGB vision experiment."""
import argparse
from pathlib import Path
import signal
import time

from train_smoke import torch
import torchvision
from runtime_files import ROOT, atomic_json, digest, read_json, status
from state_data import StateStore
from state_model import make_models, normalize, state_counts, state_loss, summarize_counts
from train import load_checkpoint, save_checkpoint


def contract(config, dataset, device):
    sources = ('tools/learning/train_state.py', 'tools/learning/state_model.py', 'tools/learning/state_data.py', 'src/yt2slp/state_plan.py')
    return {'kind': 'matched-state-vision-v1', 'dataset_sha256': digest(dataset),
        'code': {p: digest(ROOT/p) for p in sources}, 'encoder_weights_sha256': digest(ROOT/config['encoder_weights']),
        'torch_version': str(torch.__version__), 'torchvision_version': str(torchvision.__version__), 'device': device,
        'hyperparameters': {k: config[k] for k in ('batch_size', 'learning_rate', 'encoder_learning_rate', 'seed')},
        'protocol': 'same RGB, setup, initial heads, batches, updates and fixed BN; only final CNN block trainable in finetuned branch'}


def evaluate(prefix, models, store, device, batch_size):
    for model in models.values(): model.eval()
    aggregate = {name: None for name in models}
    with torch.no_grad():
        for start in range(0, store.total, batch_size):
            indices = list(range(start, min(start+batch_size, store.total))); batch = store.batch(indices)
            features = prefix(normalize(batch['images'], device)); setup = batch['setup'].to(device)
            predictions = {name: model(features, setup) for name, model in models.items()}
            targets = {k: v.to(device) for k, v in store.batch(indices, 'targets').items()}
            for name, prediction in predictions.items():
                counts = state_counts(prediction, targets)
                if aggregate[name] is None: aggregate[name] = counts
                else:
                    for key in counts: aggregate[name][key] += counts[key]
    for model in models.values(): model.train()
    return {name: summarize_counts(counts) for name, counts in aggregate.items()}


def train(config, run, device_name='cuda', max_steps=None, factory=make_models):
    import json
    run.mkdir(parents=True, exist_ok=True); progress = run/'status.json'; stop = [None]
    def request(signum, frame): stop[0] = 'stop'
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, request)
    status(progress, 'loading', step=read_json(run/'latest.json', {}).get('step', 0))
    torch.set_num_threads(config['threads']); torch.manual_seed(config['seed']); device = torch.device(device_name)
    if device.type == 'cuda':
        if not torch.cuda.is_available(): raise ValueError('CUDA unavailable; no fallback')
        torch.cuda.set_per_process_memory_fraction(config['gpu_memory_fraction']); torch.cuda.manual_seed_all(config['seed'])
    dataset = ROOT/config['data_directory']/'dataset.json'; expected = contract(config, dataset, device_name)
    training = StateStore(dataset, 'train'); validation = StateStore(dataset, 'validation', training.dataset)
    prefix, models = factory(ROOT/config['encoder_weights']); prefix = prefix.to(device).eval().requires_grad_(False)
    optimizers = {}
    for name, model in models.items():
        model.to(device).train(); heads = [p for key, p in model.named_parameters() if not key.startswith('last.')]
        groups = [{'params': heads, 'lr': config['learning_rate']}]
        if name == 'finetuned': groups.append({'params': model.last.parameters(), 'lr': config['encoder_learning_rate']})
        optimizers[name] = torch.optim.AdamW(groups)
    sampler = torch.Generator().manual_seed(config['seed']+1); step = 0; best = None; latest_validation = None; losses = {}
    restored = load_checkpoint(run, expected)
    if restored:
        for name, model in models.items():
            model.load_state_dict(restored['models'][name], strict=True); optimizers[name].load_state_dict(restored['optimizers'][name])
        step = restored['step']; best = restored['best_score']; latest_validation = restored['validation']
        sampler.set_state(restored['sampler_rng']); torch.set_rng_state(restored['torch_rng'])
        if device.type == 'cuda': torch.cuda.set_rng_state_all(restored['cuda_rng'])
    limit = config['max_steps'] if max_steps is None else max_steps
    if limit < step: raise ValueError('total step limit precedes checkpoint')
    atomic_json(run/'contract.json', expected); began = time.monotonic(); start = step
    def checkpoint(improved=False):
        return save_checkpoint(run, {'schema': 1, 'kind': 'matched-state-vision-trainer', 'step': step, 'contract': expected,
            'models': {n: m.state_dict() for n, m in models.items()}, 'optimizers': {n: o.state_dict() for n, o in optimizers.items()},
            'sampler_rng': sampler.get_state(), 'torch_rng': torch.get_rng_state(),
            'cuda_rng': torch.cuda.get_rng_state_all() if device.type == 'cuda' else [],
            'best_score': best, 'validation': latest_validation}, improved)
    def report(state, **more):
        return status(progress, state, step=step, max_steps=limit, train_images=training.total, validation_images=validation.total,
            training_loss=losses, latest_validation=latest_validation, best_validation_action_macro=best,
            steps_per_second=(step-start)/max(time.monotonic()-began, .001), device=device_name, **more)
    report('running', resumed_from_step=step)
    while True:
        wanted = stop[0] or read_json(run/'control.json', {}).get('command')
        if wanted in ('pause', 'stop'):
            saved = checkpoint(); report('paused' if wanted == 'pause' else 'stopped', checkpoint=saved); return
        if step >= limit: checkpoint(); report('completed'); return
        indices = torch.randint(training.total, (config['batch_size'],), generator=sampler).tolist()
        batch = training.batch(indices); setup = batch['setup'].to(device)
        with torch.no_grad(): features = prefix(normalize(batch['images'], device))
        targets = {k: v.to(device) for k, v in training.batch(indices, 'targets').items()}
        for name, model in models.items():
            optimizer = optimizers[name]; optimizer.zero_grad(set_to_none=True)
            loss = state_loss(model(features, setup), targets)
            if not torch.isfinite(loss): raise ValueError('non-finite state loss')
            loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 5); optimizer.step(); losses[name] = float(loss.detach())
        step += 1
        if step % config['evaluate_every'] == 0:
            report('evaluating'); latest_validation = evaluate(prefix, models, validation, device, config['batch_size'])
            score = latest_validation['finetuned']['action_macro_recall']; improved = score is not None and (best is None or score > best)
            if improved: best = score
            saved = checkpoint(improved)
            with (run/'metrics.ndjson').open('a') as handle:
                handle.write(json.dumps({'step': step, 'validation': latest_validation, 'checkpoint': saved, 'unix': time.time()})+'\n')
            print(json.dumps({'step': step, 'validation': latest_validation}), flush=True)
        elif step % config['checkpoint_every'] == 0: checkpoint()
        if step % config['log_every'] == 0: print(json.dumps(report('running')), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--steps', type=int); args = parser.parse_args(); config = read_json(args.config); run = ROOT/config['run_directory']
    try: train(config, run, max_steps=args.steps)
    except BaseException as error:
        old = read_json(run/'status.json', {}); old.pop('state', None); old.pop('updated_unix', None); old.pop('error', None)
        status(run/'status.json', 'failed', **old, error=str(error)); raise


if __name__ == '__main__': main()
