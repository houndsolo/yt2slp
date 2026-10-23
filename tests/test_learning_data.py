"""Pairing metadata fixtures, not fabricated replay files or simulated gameplay."""
from copy import deepcopy
from fractions import Fraction
import json

import pytest

from yt2slp.learning_data import build_pairs, validate_split_plan, window_centers
from yt2slp.video import sha256


@pytest.fixture
def prepared(tmp_path):
    video = tmp_path/'video'
    decoded = video/'ingested'
    decoded.mkdir(parents=True)
    (video/'source.mp4').write_bytes(b'identity-only video fixture, never decoded')
    frames, mapping, targets = [], [], []
    for i in range(5):
        image = decoded/f'{i}.png'
        image.write_bytes(f'identity-only image fixture {i}'.encode())
        frames.append({'index': i, 'pts': i*256, 'relative_seconds': str(Fraction(i, 60)),
            'time_seconds': str(Fraction(i, 60)), 'image': image.name, 'image_sha256': sha256(image)})
        mapping.append({'video_frame': i, 'replay_frame': i+1, 'literal_timer': str(i)})
        targets.extend({'frame': i+1, 'port': p} for p in (0, 2))
    doc = {'schema': 1, 'kind': 'local-video', 'source_sha256': sha256(video/'source.mp4'),
        'width': 642, 'height': 528, 'time_base': '1/15360', 'frames': frames}
    (decoded/'video.json').write_text(json.dumps(doc))
    (video/'capture-index.json').write_text(json.dumps(mapping))
    provenance = {'kind': 'supplied-replay-source-video', 'passed': True, 'interval': [1, 5],
        'source_replay_sha256': 'a'*64, 'supplied_setup': {'replay_sha256': 'a'*64},
        'video_sha256': doc['source_sha256'], 'identities': {
            '/work/old-path/video.json': sha256(decoded/'video.json'),
            '/work/old-path/capture-index.json': sha256(video/'capture-index.json')}}
    (video/'source-provenance.json').write_text(json.dumps(provenance))
    labels = tmp_path/'labels.json'
    labels.write_text(json.dumps({'schema': 1, 'kind': 'supervised-replay-labels',
        'replay_sha256': 'a'*64, 'settings': {'players': [{'port': 0}, {'port': 2}]}, 'rows': targets}))
    plan = tmp_path/'plan.json'
    plan.write_text(json.dumps({'schema': 1, 'matches': [
        {'replay_sha256': 'a'*64, 'split': 'train', 'group': 'day-1', 'previously_examined': True},
        {'replay_sha256': 'b'*64, 'split': 'validation', 'group': 'day-2'}]}))
    return video, labels, plan, tmp_path/'out'


def test_pairs_preserve_keys_masks_ports_and_whole_match_split(prepared):
    result = build_pairs(*prepared, context=3)
    assert result['split'] == 'train' and result['group'] == 'day-1'
    assert result['ports'] == [0, 2] and result['window_centers'] == [1, 2, 3]
    assert len(result['frames']) == 5
    assert not result['training_ready']
    assert result['timing'] == {'timer_frame_mapping_verified': True, 'candidate_image_to_post_offset': 0,
        'image_post_phase_verified': False, 'native_vi_adapter_verified': False}
    output = prepared[-1]
    for i, row in enumerate(result['frames']):
        assert row['replay_frame'] == i+1 and row['pts'] == i*256
        assert sha256(output/row['image']) == row['image_sha256']
        assert row['targets'] == [{'frame': i+1, 'port': 0}, {'frame': i+1, 'port': 2}]
    with pytest.raises(FileExistsError):
        build_pairs(*prepared, context=3)


@pytest.mark.parametrize('change', ['replay', 'mapping', 'timestamp', 'image', 'target', 'duplicate', 'video'])
def test_identity_or_sample_corruption_fails_before_publishing(prepared, change):
    video, labels, plan, output = prepared
    if change in ('target', 'duplicate'):
        path = labels
        doc = json.loads(path.read_text())
        if change == 'target':
            doc['rows'].pop()
        else:
            doc['rows'].append(doc['rows'][0])
    elif change == 'replay':
        path = video/'source-provenance.json'
        doc = json.loads(path.read_text()); doc['source_replay_sha256'] = 'b'*64
    elif change == 'mapping':
        path = video/'capture-index.json'
        doc = json.loads(path.read_text()); doc[2]['replay_frame'] += 1
    elif change == 'timestamp':
        path = video/'ingested/video.json'
        doc = json.loads(path.read_text()); doc['frames'][2]['pts'] += 1
    else:
        path = video/('ingested/2.png' if change == 'image' else 'source.mp4')
        path.write_bytes(b'corrupt')
        doc = None
    if doc is not None:
        path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        build_pairs(*prepared, context=3)
    assert not output.exists()


def test_split_plan_rejects_leakage_and_relabelled_development_matches(prepared):
    plan = json.loads(prepared[2].read_text())
    for edit in ('group', 'identity', 'examined'):
        bad = deepcopy(plan)
        if edit == 'group':
            bad['matches'][1]['group'] = 'day-1'
        elif edit == 'identity':
            bad['matches'][1]['replay_sha256'] = 'a'*64
        else:
            bad['matches'][0]['split'] = 'test'
        with pytest.raises(ValueError):
            validate_split_plan(bad)


def test_context_windows_never_cross_missing_frames():
    rows = [{'replay_frame': f} for f in [1, 2, 3, 5, 6, 7]]
    assert window_centers(rows, 3) == [1, 4]
    for context in (2, True, 0):
        with pytest.raises(ValueError):
            window_centers(rows, context)
