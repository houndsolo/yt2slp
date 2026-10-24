"""Multiple bounded clips per replay, with stable physical-port slots and mirrors.

The legacy trainer/data reader are intentionally unchanged so old checkpoints
remain usable. Their memory-mapped batch implementation is shared here.
"""
from collections import OrderedDict

from runtime_files import digest, read_json
from stream_data import WindowStore
from yt2slp.corpus import corpus_ports
from yt2slp.learning_data import validate_split_plan


class CorpusStore(WindowStore):
    def __init__(self, manifest, split, resident_clips=8):
        from pathlib import Path
        self.path=Path(manifest); self.dataset=read_json(self.path)
        if (self.dataset.get('schema')!=1 or self.dataset.get('kind')!='vision-corpus-feature-dataset'
                or self.dataset.get('slot_mapping')!='ascending-physical-ports' or self.dataset.get('stage')!=31):
            raise ValueError('versioned physical-port corpus dataset required')
        plan_path=self.path.parent/self.dataset['split_plan']; selection_path=self.path.parent/self.dataset['selection']
        if digest(plan_path)!=self.dataset['split_plan_sha256'] or digest(selection_path)!=self.dataset['selection_sha256']:
            raise ValueError('frozen corpus plan/selection changed')
        membership=validate_split_plan(read_json(plan_path))
        chosen={c['clip_id']:c for c in read_json(selection_path)['clips']}
        seen=set(); intervals={}
        for shard in self.dataset['shards']:
            source=membership.get(shard['replay_sha256']); selected=chosen.get(shard['clip_id'])
            if (shard['split'] not in ('train','validation') or not source or not selected
                    or any(shard[k]!=source[k] or selected[k]!=shard[k] for k in ('split','group','replay_sha256'))
                    or selected['interval']!=shard['interval'] or shard['clip_id'] in seen):
                raise ValueError('duplicate clip, test leakage or changed corpus membership')
            if (corpus_ports(source)!=shard['slot_ports'] or shard['slot_characters']!=[
                    p['character'] for p in sorted(source['players'],key=lambda p:p['port'])]):
                raise ValueError('physical-port ordering or roster changed')
            seen.add(shard['clip_id']); first,last=shard['interval']
            if (not any(c['interval']==[first,last] and c['clip_id']==shard['clip_id'] for c in source['clips'])
                    or shard['frames']!=last-first+1 or shard['first_frame']!=first
                    or shard['context_frames']!=self.dataset['context_frames']
                    or shard['windows']!=shard['frames']-shard['context_frames']+1
                    or shard['windows']<=0 or shard['feature_size']!=3072):
                raise ValueError('invalid corpus clip boundaries or dimensions')
            for a,b in intervals.setdefault(shard['replay_sha256'],[]):
                if first<=b and a<=last: raise ValueError('overlapping corpus clips')
            intervals[shard['replay_sha256']].append((first,last))
            if digest(self.path.parent/shard['payload'])!=shard['payload_sha256']:
                raise ValueError('corpus feature shard identity changed')
        self.shards=[s for s in self.dataset['shards'] if s['split']==split]
        if not self.shards: raise ValueError(f'no {split} corpus windows')
        self.ends=[]; self.total=0
        for shard in self.shards: self.total+=shard['windows']; self.ends.append(self.total)
        self.cache=OrderedDict(); self.resident_clips=resident_clips
