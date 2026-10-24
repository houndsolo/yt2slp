"""Frozen development diagnostics; no training, fitted thresholds or final tests."""
import argparse
from pathlib import Path

from train_smoke import torch
from baseline import BUTTONS
from runtime_files import ROOT, atomic_json, digest, read_json, status
from review_run import snapshot
from sequence_data import SequenceStore
from sequence_model import SequenceProposal, hard_controls, sequence_metrics
from train_sequence import contract, infer_clip
from yt2slp.event_analysis import event_counts, rates


def merge(target, values):
    for key, value in values.items(): target[key] = target.get(key, 0)+value


def analyze(prediction, targets, first):
    controls, _ = hard_controls(prediction); guessed = controls[0]; truth = targets['buttons'][0, 1:].bool()
    valid = targets['buttons_mask'][0, 1:]; per_button = {}
    for button, name in enumerate(BUTTONS):
        heads = {}
        for head, label in enumerate(('hold', 'press', 'release')):
            counts = {}
            for port in range(2):
                a, g, mask = truth[:, port, head, button], guessed[:, port, head, button], valid[:, port, head, button]
                if head == 0:
                    merge(counts, {'tp': int((a & g & mask).sum()), 'fp': int((~a & g & mask).sum()), 'fn': int((a & ~g & mask).sum())})
                else:
                    p = [first+int(i) for i in (g & mask).nonzero().flatten().tolist()]
                    t = [first+int(i) for i in (a & mask).nonzero().flatten().tolist()]
                    for tolerance in (0, 1, 2): merge(counts.setdefault(str(tolerance), {}), event_counts(p, t, tolerance))
            heads[label] = counts
        per_button[name] = heads
    return per_button


def total_heads(per_button, tolerance=0):
    result = {}
    for head in ('hold', 'press', 'release'):
        counts = {}
        for values in per_button.values(): merge(counts, values[head] if head == 'hold' else values[head][str(tolerance)])
        result[head] = rates(counts)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); config = read_json(args.config); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    progress = output/'status.json'
    try:
        if not torch.cuda.is_available(): raise ValueError('CUDA unavailable; no fallback')
        torch.set_num_threads(config['threads']); torch.cuda.set_per_process_memory_fraction(.8)
        dataset = ROOT/config['data_directory']/'dataset.json'
        training = SequenceStore(dataset, 'train', config['sequence_frames']); store = SequenceStore(dataset, 'validation', config['sequence_frames'])
        payload, pointer = snapshot(ROOT/config['run_directory'], output, 'best', contract(config, dataset, 'cuda'))
        weights = training.button_weights(); network = SequenceProposal(3072, config['hidden_size']).cuda()
        network.load_state_dict(payload['model'], strict=True); network.eval()
        aggregate = {mode: {b: {h: ({} if h == 'hold' else {str(t): {} for t in (0, 1, 2)})
            for h in ('hold', 'press', 'release')} for b in BUTTONS} for mode in ('raw', 'training-weight-offset')}
        clips = []; swapped_counts = {}; ordinary_counts = {}
        for index, shard in enumerate(store.shards):
            status(progress, 'inferring', clip=index+1, total=len(store.shards))
            cached = store.load(index); half = config['context_frames']//2
            prediction = infer_clip(network, cached['features'], config['context_frames'], torch.device('cuda'),
                config['batch_size']*(config['sequence_frames']+1))
            frozen = output/f'predictions-{index:03d}.pt'; torch.save(prediction, frozen)
            # Supervision is accessed after the image-feature-only output is frozen.
            targets = {k: v[half:shard['frames']-half].unsqueeze(0) for k, v in cached['targets'].items()}
            analyses = {}
            for mode in aggregate:
                adjusted = dict(prediction)
                if mode != 'raw': adjusted['held'] = prediction['held']-weights[:, 0].log()
                analysis = analyze(adjusted, targets, shard['first_frame']+half+1); analyses[mode] = total_heads(analysis)
                for button, heads in analysis.items():
                    for head, values in heads.items():
                        if head == 'hold': merge(aggregate[mode][button][head], values)
                        else:
                            for tolerance, counts in values.items(): merge(aggregate[mode][button][head][tolerance], counts)
            normal = sequence_metrics(prediction, targets)['button_metrics']
            swapped = sequence_metrics({k: v.flip(2) for k, v in prediction.items()}, targets)['button_metrics']
            for head in normal:
                merge(ordinary_counts.setdefault(head, {}), normal[head]); merge(swapped_counts.setdefault(head, {}), swapped[head])
            clips.append({'clip_id': shard['clip_id'], 'roster': shard['slot_characters'], 'predictions_sha256': digest(frozen),
                'metrics': analyses, 'slot_swap_diagnostic': {h: {'ordinary': rates(normal[h]), 'swapped': rates(swapped[h])} for h in normal}})
        result = {'schema': 1, 'kind': 'sequence-development-error-report', 'checkpoint': pointer,
            'dataset_sha256': digest(dataset), 'held_positive_weights': weights[:, 0].tolist(),
            'modes': {mode: {'exact': total_heads(values), 'within_one_frame': total_heads(values, 1),
                'within_two_frames': total_heads(values, 2), 'per_button': {b: {h: rates(v) if h == 'hold' else
                    {t: rates(c) for t, c in v.items()} for h, v in heads.items()} for b, heads in values.items()}}
                for mode, values in aggregate.items()},
            'slot_swap_diagnostic': {'ordinary': {h: rates(c) for h, c in ordinary_counts.items()},
                'always_swapped': {h: rates(c) for h, c in swapped_counts.items()},
                'policy': 'diagnostic only; no label-selected permutation enters inference or primary metrics'},
            'clips': clips, 'test_matches_opened': 0,
            'policy': 'full development split; fixed raw threshold and train-weight offsets declared before labels; '
                'offset is a diagnostic, not calibrated probability under the edge loss; one-to-one timing matches never modify predictions'}
        expected = payload['validation']['button_metrics']
        for head in expected:
            for count in ('tp', 'fp', 'fn'):
                if result['modes']['raw']['exact'][head][count] != expected[head][count]:
                    raise ValueError('raw diagnostic did not reproduce saved validation counts')
        atomic_json(output/'report.json', result); status(progress, 'complete', checkpoint_step=payload['step'], clips=len(clips))
        print({mode: data['exact'] for mode, data in result['modes'].items()}, flush=True)
    except BaseException as error:
        status(progress, 'failed', error=str(error)); raise


if __name__ == '__main__': main()
