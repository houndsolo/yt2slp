"""Small RGB caches with image inputs physically separate from state answers."""
from bisect import bisect_right
from collections import OrderedDict
from pathlib import Path

from train_smoke import torch
from runtime_files import digest, read_json
from yt2slp.state_plan import select_state_clips


class StateStore:
    def __init__(self, manifest, split, verified=None):
        self.path = Path(manifest); self.dataset = verified or read_json(self.path)
        doc = self.dataset
        if doc.get('kind') != 'matched-state-rgb-dataset' or doc.get('test_matches_opened') != 0:
            raise ValueError('matched development RGB dataset required')
        source = self.path.parent/doc['source_dataset']
        if digest(source) != doc['source_dataset_sha256']: raise ValueError('source corpus changed')
        selection = {s['clip_id']: s for s in select_state_clips(read_json(source), doc['frame_stride'])}
        seen = set(); roles = {}
        for shard in doc['shards']:
            original = selection.get(shard['clip_id']); replay = shard['replay_sha256']
            if (not original or shard['clip_id'] in seen or any(shard[k] != original[k] for k in ('split', 'replay_sha256', 'group'))
                    or shard['frames'] != len(original['selected_indices']) or shard['selected_indices'] != original['selected_indices']):
                raise ValueError('changed selection, membership or duplicate state clip')
            if replay in roles and roles[replay] != shard['split']: raise ValueError('state replay crosses splits')
            roles[replay] = shard['split']; seen.add(shard['clip_id'])
            if verified is None:
                for key in ('inputs', 'targets', 'view'):
                    if digest(self.path.parent/shard[key]) != shard[key+'_sha256']: raise ValueError('state cache identity changed')
        if set(selection) != seen: raise ValueError('incomplete state image selection')
        self.shards = [s for s in doc['shards'] if s['split'] == split]
        if not self.shards: raise ValueError('empty state split')
        self.ends = []; self.total = 0
        for shard in self.shards: self.total += shard['frames']; self.ends.append(self.total)
        self.cache = OrderedDict()

    def load(self, index, kind):
        key = index, kind
        if key in self.cache: self.cache.move_to_end(key); return self.cache[key]
        payload = torch.load(self.path.parent/self.shards[index][kind], map_location='cpu', weights_only=True, mmap=True)
        if kind == 'inputs' and (payload['images'].dtype != torch.uint8 or tuple(payload['images'].shape) != (self.shards[index]['frames'], 3, 320, 384)):
            raise ValueError('cached RGB shape/type changed')
        if kind == 'targets' and any(tuple(v.shape) != (self.shards[index]['frames'], 2) for v in payload.values()):
            raise ValueError('cached state target shape changed')
        self.cache[key] = payload
        if len(self.cache) > 24: self.cache.popitem(last=False)
        return payload

    def batch(self, indices, kind='inputs'):
        grouped = {}; rows = {}; indices = list(indices)
        for position, number in enumerate(indices):
            if type(number) is not int or not 0 <= number < self.total: raise ValueError('state image index outside split')
            shard = bisect_right(self.ends, number); local = number-(self.ends[shard-1] if shard else 0)
            grouped.setdefault(shard, []).append((position, local))
        for shard, requests in grouped.items():
            payload = self.load(shard, kind)
            for position, local in requests:
                for key, value in payload.items():
                    rows.setdefault(key, [None]*len(indices))[position] = value[local]
        return {k: torch.stack(v) for k, v in rows.items()}
