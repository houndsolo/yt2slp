"""Contiguous supervised sequences, each with a preceding image-state seed."""
from bisect import bisect_right

import torch
from corpus_data import CorpusStore


class SequenceStore(CorpusStore):
    def __init__(self, manifest, split, sequence_frames, resident_clips=8):
        super().__init__(manifest, split, resident_clips)
        if type(sequence_frames) is not int or not 2 <= sequence_frames <= 64:
            raise ValueError('sequence length must be 2..64 supervised frames')
        self.sequence_frames = sequence_frames; self.ends = []; self.total = 0
        for shard in self.shards:
            count = shard['windows']-sequence_frames
            if count < 1: raise ValueError('clip too short for context, seed and supervised sequence')
            self.total += count; self.ends.append(self.total)

    def batch(self, indices):
        grouped = {}; features = [None]*len(indices); targets = {}
        for position, number in enumerate(indices):
            if type(number) is not int or not 0 <= number < self.total: raise ValueError('sequence index outside split')
            shard = bisect_right(self.ends, number); start = number-(self.ends[shard-1] if shard else 0)
            grouped.setdefault(shard, []).append((position, start))
        for shard, requests in grouped.items():
            payload = self.load(shard); context = self.shards[shard]['context_frames']; n = self.sequence_frames+1
            for position, start in requests:
                # n neighboring center predictions, each retaining the exact
                # same fixed context as inference. Never bridge a clip boundary.
                features[position] = torch.stack([payload['features'][start+i:start+i+context] for i in range(n)])
                center = start+context//2
                for key, value in payload['targets'].items():
                    targets.setdefault(key, [None]*len(indices))[position] = value[center:center+n]
        return torch.stack(features), {k: torch.stack(v) for k, v in targets.items()}
