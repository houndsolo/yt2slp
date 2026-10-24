from copy import deepcopy
import pytest

from yt2slp.state_plan import select_state_clips, setup_vectors


def test_setup_supplies_costume_to_physical_port_mapping_for_mirrors():
    settings = {'stage': 31, 'players': [{'port': 3, 'character': 2, 'costume': 2}, {'port': 1, 'character': 2, 'costume': 0}]}
    a, b = setup_vectors(settings)
    assert a[0] == b[0] == 1 and a[2] == b[4] == 1 and a[11] == b[13] == 1
    assert sum(a) == sum(b) == 3
    bad = deepcopy(settings); bad['players'][0]['costume'] = 8
    with pytest.raises(ValueError): setup_vectors(bad)


def test_selection_is_settings_only_one_clip_per_match_and_keeps_original_frames():
    dataset = {'kind': 'vision-corpus-feature-dataset', 'test_matches_opened': 0, 'shards': [
        {'clip_id': clip, 'replay_sha256': replay, 'split': split, 'group': split, 'frames': 20}
        for clip, replay, split in [('b', 'a', 'train'), ('a', 'a', 'train'), ('c', 'b', 'validation')]]}
    chosen = select_state_clips(dataset, 6)
    assert [s['clip_id'] for s in chosen] == ['a', 'c']
    assert all(s['selected_indices'] == [0, 6, 12, 18] for s in chosen)
    bad = deepcopy(dataset); bad['shards'][0]['split'] = 'test'
    with pytest.raises(ValueError): select_state_clips(bad, 6)
    bad = deepcopy(dataset); bad['shards'][0]['split'] = 'validation'
    with pytest.raises(ValueError): select_state_clips(bad, 6)
