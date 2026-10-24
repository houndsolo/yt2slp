"""Prepare a score-independent sparse RGB/state experiment from verified clips."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil

from PIL import Image, ImageOps
from train_smoke import torch
from corpus_data import CorpusStore
from runtime_files import ROOT, atomic_json, digest, read_json, status
from yt2slp.state_plan import select_state_clips, setup_vectors


def cache_clip(shard, source, output, config):
    folder = output/'clips'/shard['clip_id']; folder.mkdir(parents=True, exist_ok=True)
    previous = read_json(folder/'shard.json')
    if previous:
        for key in ('inputs', 'targets', 'view'):
            if digest(output/previous[key]) != previous[key+'_sha256']: raise ValueError('completed state cache changed')
        return previous
    if shutil.disk_usage(ROOT).free < config['minimum_free_gib']*2**30: raise ValueError('disk reserve reached')
    view_path = (source.parent/shard['payload']).parent/'images.json'
    if digest(view_path) != shard['image_view_sha256']: raise ValueError('original image view changed')
    view = read_json(view_path); setup = torch.tensor(setup_vectors(view['settings']), dtype=torch.float32)
    images = []; frames = []
    for index in shard['selected_indices']:
        frame = view['frames'][index]; path = view_path.parent/frame['image']
        if digest(path) != frame['image_sha256']: raise ValueError('source PNG changed')
        with Image.open(path) as image:
            image = ImageOps.pad(image.convert('RGB'), (384, 320), method=Image.Resampling.BILINEAR)
            images.append(torch.frombuffer(bytearray(image.tobytes()), dtype=torch.uint8).reshape(320, 384, 3).permute(2, 0, 1).contiguous())
        frames.append({**frame, 'image': os.path.relpath(path, folder)})
    target_path = ROOT/shard['labels']
    if digest(target_path) != shard['labels_sha256']: raise ValueError('original state labels changed')
    labels = read_json(target_path); keyed = {(r['frame'], r['port']): r for r in labels['rows']}
    ports = shard['slot_ports']; targets = {k: [] for k in ('action', 'action_mask', 'airborne', 'airborne_mask')}
    for frame in frames:
        values = [keyed[frame['replay_frame'], port]['state'] for port in ports]
        for field in ('action', 'airborne'):
            masks = [row['mask'][field] for row in values]
            row = [item['values'][field] if valid else 0 for item, valid in zip(values, masks)]
            if field == 'action' and any(valid and (type(value) is not int or not 0 <= value < 512) for value, valid in zip(row, masks)):
                raise ValueError('action outside vocabulary')
            targets[field].append(row); targets[field+'_mask'].append(masks)
    tensors = {k: torch.tensor(v, dtype=torch.bool if k.endswith('_mask') else torch.long if k == 'action' else torch.float32)
               for k, v in targets.items()}
    payload = {'images': torch.stack(images), 'setup': setup.unsqueeze(0).expand(len(images), -1, -1).clone()}
    for name, value in (('inputs', payload), ('targets', tensors)):
        temporary = folder/(name+'.tmp'); torch.save(value, temporary); temporary.replace(folder/(name+'.pt'))
    atomic_json(folder/'view.json', {**view, 'frames': frames, 'source_view_sha256': digest(view_path),
        'selection': 'original signed frames sampled by fixed stride; no temporal interpolation', 'frame_stride': config['frame_stride']})
    result = {k: shard[k] for k in ('clip_id', 'replay_sha256', 'split', 'group', 'selected_indices', 'slot_ports', 'slot_characters')}
    result['frames'] = len(images)
    for name in ('inputs', 'targets', 'view'):
        path = folder/(name+('.json' if name == 'view' else '.pt'))
        result[name] = str(path.relative_to(output)); result[name+'_sha256'] = digest(path)
    atomic_json(folder/'shard.json', result); return result


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args(); config = read_json(args.config); output = ROOT/config['data_directory']; output.mkdir(parents=True, exist_ok=True)
    progress = output/'preparation-status.json'
    try:
        torch.set_num_threads(1); source = ROOT/config['source_data_directory']/'dataset.json'
        CorpusStore(source, 'train')  # Verify the original corpus and reserved split before selection.
        selected = select_state_clips(read_json(source), config['frame_stride'])
        identity = {'source_dataset_sha256': digest(source), 'config_sha256': digest(args.config),
            'code': {str(p): digest(ROOT/p) for p in ('tools/learning/prepare_state.py', 'src/yt2slp/state_plan.py')},
            'policy': 'one first-sorted audited clip per development match; fixed stride before state labels/scores'}
        old = read_json(output/'preparation-contract.json')
        if old and old != identity: raise ValueError('state preparation contract changed; use new data directory')
        atomic_json(output/'preparation-contract.json', identity); completed = []
        status(progress, 'preparing', finished=0, total=len(selected))
        with ThreadPoolExecutor(max_workers=config['preparation_workers']) as pool:
            for shard in pool.map(lambda s: cache_clip(s, source, output, config), selected):
                completed.append(shard); status(progress, 'preparing', finished=len(completed), total=len(selected))
        manifest = {'schema': 1, 'kind': 'matched-state-rgb-dataset', 'source_dataset': os.path.relpath(source, output),
            'source_dataset_sha256': digest(source), 'frame_stride': config['frame_stride'], 'shards': completed,
            'test_matches_opened': 0, 'preparation_contract_sha256': digest(output/'preparation-contract.json')}
        atomic_json(output/'dataset.json', manifest)
        status(progress, 'ready', finished=len(completed), total=len(selected),
            images={role: sum(s['frames'] for s in completed if s['split'] == role) for role in ('train', 'validation')})
    except BaseException as error:
        status(progress, 'failed', error=str(error)); raise


if __name__ == '__main__': main()
