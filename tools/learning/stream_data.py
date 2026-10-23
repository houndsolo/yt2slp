"""Memory-mapped clip shards; materialize only the requested temporal batch."""
from bisect import bisect_right
from collections import OrderedDict
from pathlib import Path

import torch
from runtime_files import digest, read_json
from yt2slp.learning_data import validate_split_plan


class WindowStore:
    def __init__(self, manifest, split, resident_clips=2):
        self.path = Path(manifest); self.dataset = read_json(self.path)
        if (self.dataset.get('kind')!='vision-feature-dataset' or self.dataset.get('schema')!=1
                or self.dataset['slot_characters']!=[2,20] or self.dataset['stage']!=31):
            raise ValueError('versioned known-roster feature dataset required')
        shards = self.dataset['shards']; membership = {}; groups = {}
        if not {'selection','selection_sha256','split_plan','split_plan_sha256'} <= self.dataset.keys():
            raise ValueError('identity-bound split plan and selection required')
        plan_path = self.path.parent/self.dataset['split_plan']; selection_path = self.path.parent/self.dataset['selection']
        if digest(plan_path)!=self.dataset['split_plan_sha256'] or digest(selection_path)!=self.dataset['selection_sha256']:
            raise ValueError('split/selection identity changed')
        reserved = validate_split_plan(read_json(plan_path))
        selected = {s['replay_sha256']:s for s in read_json(selection_path)['matches']}
        if set(selected)!={s['replay_sha256'] for s in shards}: raise ValueError('dataset differs from frozen selection')
        for shard in shards:
            if shard['split'] not in ('train','validation'): raise ValueError('test shard must never enter training dataset')
            original = reserved.get(shard['replay_sha256']); chosen = selected[shard['replay_sha256']]
            if (not original or any(original[k]!=shard[k] or chosen[k]!=shard[k] for k in ('group','split'))):
                raise ValueError('shard membership differs from frozen plan/selection')
            if shard['replay_sha256'] in membership: raise ValueError('duplicate replay shard')
            membership[shard['replay_sha256']] = shard['split']
            if shard['group'] in groups and groups[shard['group']]!=shard['split']: raise ValueError('date group crosses splits')
            groups[shard['group']] = shard['split']
            if (shard['context_frames']!=self.dataset['context_frames'] or shard['windows']!=shard['frames']-shard['context_frames']+1
                    or shard['feature_size']!=3072 or shard['windows']<=0): raise ValueError('invalid shard dimensions/context')
            if digest(self.path.parent/shard['payload'])!=shard['payload_sha256']: raise ValueError('feature shard identity changed')
        self.shards = [s for s in shards if s['split']==split]
        if not self.shards: raise ValueError(f'no {split} windows')
        self.ends = []; total = 0
        for shard in self.shards: total += shard['windows']; self.ends.append(total)
        self.total = total; self.cache = OrderedDict(); self.resident_clips = resident_clips

    def load(self,index):
        if index in self.cache: self.cache.move_to_end(index); return self.cache[index]
        shard = self.shards[index]
        payload = torch.load(self.path.parent/shard['payload'],map_location='cpu',weights_only=True,mmap=True)
        if (payload['replay_sha256']!=shard['replay_sha256'] or payload['features'].shape!=(shard['frames'],3072)
                or any(len(v)!=shard['frames'] for v in payload['targets'].values())):
            raise ValueError('feature/target payload differs from manifest')
        self.cache[index] = payload
        if len(self.cache)>self.resident_clips: self.cache.popitem(last=False)
        return payload

    def batch(self,indices):
        indices = list(indices); features = [None]*len(indices); targets = {}; grouped = {}
        for position,number in enumerate(indices):
            index = bisect_right(self.ends,int(number))
            if not 0<=int(number)<self.total: raise ValueError('window index outside split')
            start = int(number)-(self.ends[index-1] if index else 0)
            grouped.setdefault(index,[]).append((position,start))
        # Open each shard once per minibatch, even when randomly sampled windows
        # alternate between more clips than the small resident cache can hold.
        for index,requests in grouped.items():
            context = self.shards[index]['context_frames']
            payload = self.load(index)
            for position,start in requests:
                center = start+context//2
                features[position] = payload['features'][start:start+context]
                for key,value in payload['targets'].items():
                    targets.setdefault(key,[None]*len(indices))[position] = value[center]
        return torch.stack(features),{k:torch.stack(v) for k,v in targets.items()}

    def button_weights(self):
        positive = torch.zeros(2,3,12); negative = torch.zeros_like(positive)
        for i,shard in enumerate(self.shards):
            half = shard['context_frames']//2; target = self.load(i)['targets']
            values = target['buttons'][half:shard['frames']-half]; mask = target['buttons_mask'][half:shard['frames']-half]
            positive += (values*mask).sum(0); negative += ((1-values)*mask).sum(0)
        return (negative/positive.clamp(min=1)).clamp(min=1,max=20)
