"""Settings-only sampling for a matched frozen/fine-tuned vision experiment."""
from .corpus import corpus_ports

SETUP_SIZE = 14  # character (2), costume (8), physical port (4)


def setup_vectors(settings):
    ports = corpus_ports(settings); rows = []
    for player in sorted(settings['players'], key=lambda p: p['port']):
        costume = player['costume']
        if type(costume) is not int or not 0 <= costume < 8: raise ValueError('known costume 0..7 required')
        row = [0.]*SETUP_SIZE; row[(2, 20).index(player['character'])] = 1.
        row[2+costume] = 1.; row[10+player['port']] = 1.; rows.append(row)
    if len(rows) != 2 or ports != [p['port'] for p in sorted(settings['players'], key=lambda p: p['port'])]:
        raise ValueError('two known physical players required')
    return rows


def select_state_clips(dataset, stride):
    if type(stride) is not int or not 1 <= stride <= 60: raise ValueError('frame stride must be 1..60')
    if dataset.get('kind') != 'vision-corpus-feature-dataset' or dataset.get('test_matches_opened') != 0:
        raise ValueError('verified development corpus with sealed final tests required')
    selected = []; membership = {}; groups = {}
    for shard in sorted(dataset['shards'], key=lambda s: s['clip_id']):
        replay, split, group = (shard[k] for k in ('replay_sha256', 'split', 'group'))
        if split not in ('train', 'validation'): raise ValueError('final test must not enter vision selection')
        if replay in membership and membership[replay] != split: raise ValueError('replay crosses splits')
        if group in groups and groups[group] != split: raise ValueError('date group crosses splits')
        groups[group] = split
        if replay in membership: continue
        membership[replay] = split
        selected.append({**shard, 'selected_indices': list(range(0, shard['frames'], stride))})
    return selected
