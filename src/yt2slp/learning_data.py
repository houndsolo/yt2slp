"""Identity-bound, provisional supervised pairs; no learned inference here.

Timer alignment and image/post-state phase are deliberately separate gates.
These artifacts contain original labels and belong only in training/evaluation.
"""
from fractions import Fraction
import json
import os
from pathlib import Path

from .video import sha256


def validate_split_plan(plan: dict) -> dict[str, dict]:
    if plan.get('schema') != 1 or not plan.get('matches'):
        raise ValueError('nonempty versioned whole-match split plan required')
    matches, groups = {}, {}
    for match in plan['matches']:
        digest, split, group = (match.get(k) for k in ('replay_sha256', 'split', 'group'))
        if (not isinstance(digest, str) or len(digest) != 64
                or any(c not in '0123456789abcdef' for c in digest)
                or split not in ('train', 'validation', 'test') or not isinstance(group, str) or not group):
            raise ValueError('invalid match identity, split or session group')
        if digest in matches:
            raise ValueError('duplicate replay identity in split plan')
        if group in groups and groups[group] != split:
            raise ValueError('session group crosses split boundaries')
        if split == 'test' and match.get('previously_examined', False):
            raise ValueError('examined development replay cannot be an unseen test')
        matches[digest] = match
        groups[group] = split
    return matches


def window_centers(frames: list[dict], context: int) -> list[int]:
    if type(context) is not int or context < 3 or context % 2 != 1:
        raise ValueError('odd temporal context of at least three frames required')
    half = context // 2
    return [i for i in range(half, len(frames)-half)
            if all(frames[j]['replay_frame'] == frames[i]['replay_frame']+j-i
                   for j in range(i-half, i+half+1))]


def build_pairs(video_dir: Path, labels_path: Path, plan_path: Path,
                output: Path, context: int = 31) -> dict:
    """Join the existing positive-clock official MP4 preparation with labels.

    This first exporter accepts an unmodified prepared source, never a guessed
    timer offset, resized view or arbitrary YouTube clip. It preserves 60 Hz
    samples and full-match membership before constructing temporal windows.
    """
    video_dir, labels_path, plan_path, output = (
        p.resolve() for p in (video_dir, labels_path, plan_path, output))
    video_path = video_dir/'ingested/video.json'
    provenance_path, index_path = video_dir/'source-provenance.json', video_dir/'capture-index.json'
    video, provenance, index, labels, plan = (
        json.loads(p.read_text()) for p in (video_path, provenance_path, index_path, labels_path, plan_path))
    matches = validate_split_plan(plan)
    digest = labels.get('replay_sha256')
    if labels.get('schema') != 1 or labels.get('kind') != 'supervised-replay-labels' or digest not in matches:
        raise ValueError('versioned training labels and declared whole-match membership required')
    if (provenance.get('kind') != 'supplied-replay-source-video' or provenance.get('passed') is not True
            or provenance.get('source_replay_sha256') != digest
            or provenance.get('supplied_setup', {}).get('replay_sha256') != digest
            or video.get('kind') != 'local-video' or video.get('schema') != 1
            or provenance.get('video_sha256') != video.get('source_sha256')
            or sha256(video_dir/'source.mp4') != video['source_sha256']):
        raise ValueError('video/replay preparation identity mismatch')
    # Preparation signed both the mapping and decoded image manifest. Keep that
    # chain even when /work and host paths differ; identity is the file digest.
    signed = set(provenance.get('identities', {}).values())
    if not {sha256(index_path), sha256(video_path)} <= signed:
        raise ValueError('unsigned/changed preparation mapping or video manifest')
    if (not index or len(index) != len(video['frames'])
            or provenance['interval'] != [index[0]['replay_frame'], index[-1]['replay_frame']]):
        raise ValueError('incomplete preparation frame mapping')
    ports = sorted(p['port'] for p in labels['settings']['players'])
    if len(ports) != 2 or len(set(ports)) != 2:
        raise ValueError('two distinct physical ports required')
    keyed = {}
    for row in labels['rows']:
        key = row['frame'], row['port']
        if key in keyed:
            raise ValueError('duplicate controller/state target')
        keyed[key] = row
    paired = []
    for i, (mapping, image) in enumerate(zip(index, video['frames'])):
        frame = mapping['replay_frame']
        if (mapping['video_frame'] != i or image['index'] != i or type(frame) is not int
                or frame != index[0]['replay_frame']+i
                or Fraction(image['relative_seconds']) != Fraction(i, 60)
                or Fraction(image['time_seconds']) != image['pts']*Fraction(video['time_base'])):
            raise ValueError('noncontiguous frame keys or changed 60 Hz timestamps')
        path = (video_dir/'ingested'/image['image']).resolve()
        if sha256(path) != image['image_sha256']:
            raise ValueError('decoded training image identity mismatch')
        targets = [keyed.get((frame, port)) for port in ports]
        if any(t is None for t in targets):
            raise ValueError('missing controller/state target')
        paired.append({'index': i, 'replay_frame': frame, 'pts': image['pts'],
            'time_seconds': image['time_seconds'], 'relative_seconds': image['relative_seconds'],
            'literal_timer': mapping['literal_timer'],
            'image': os.path.relpath(path, output), 'image_sha256': image['image_sha256'],
            'targets': targets})
    centers = window_centers(paired, context)
    if not centers:
        raise ValueError('clip too short for the declared temporal context')
    membership = matches[digest]
    report = {'schema': 1, 'kind': 'supervised-video-replay-pairs',
        'replay_sha256': digest, 'split': membership['split'], 'group': membership['group'],
        'settings': labels['settings'], 'ports': ports,
        'width': video['width'], 'height': video['height'], 'time_base': video['time_base'],
        'context_frames': context, 'window_centers': centers, 'frames': paired,
        'timing': {'timer_frame_mapping_verified': True, 'candidate_image_to_post_offset': 0,
            'image_post_phase_verified': False, 'native_vi_adapter_verified': False},
        'training_ready': False,
        'policy': 'provisional same-key targets; smoke tests only until image/post phase calibration; original labels never enter held-out inference',
        'identities': {name: sha256(path) for name, path in (
            ('labels', labels_path), ('split_plan', plan_path), ('video', video_path),
            ('provenance', provenance_path), ('capture_index', index_path))}}
    output.mkdir(parents=True, exist_ok=False)
    (output/'pairs.json').write_text(json.dumps(report, indent=2)+'\n')
    return report
