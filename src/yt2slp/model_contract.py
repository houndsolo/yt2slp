"""Known-roster model contract and an image-only inference view.

No replay controller/state target file is read by either operation.
"""
import json
import os
from fractions import Fraction
from pathlib import Path

from .video import sha256


def validate_image_view(view: dict, context: int) -> None:
    frames = view.get('frames', [])
    if (view.get('schema') != 1 or view.get('kind') != 'image-only-known-roster-video'
            or type(context) is not int or context < 3 or context % 2 != 1 or len(frames) < context):
        raise ValueError('versioned image-only view with sufficient odd context required')
    for i, row in enumerate(frames):
        if (row['index'] != i or type(row['replay_frame']) is not int
                or row['replay_frame'] != frames[0]['replay_frame']+i
                or (Fraction(row['pts'])-Fraction(frames[0]['pts']))*Fraction(view['time_base']) != Fraction(i, 60)):
            raise ValueError('contiguous signed frames and exact 60 Hz PTS required')


def slot_ports(model: dict, settings: dict) -> list[int]:
    """Map trained semantic slots to physical ports using supplied setup only."""
    characters = model['slot_characters']
    players = settings['players']
    if (settings.get('stage') != model['stage'] or len(players) != 2
            or len(characters) != 2 or len(set(characters)) != 2
            or sorted(p['character'] for p in players) != sorted(characters)
            or len({p['port'] for p in players}) != 2
            or any(type(p['port']) is not int or not 0 <= p['port'] <= 3 for p in players)):
        raise ValueError('known stage and two unique character/port assignments required; mirrors/doubles unsupported')
    by_character = {p['character']: p['port'] for p in players}
    return [by_character[c] for c in characters]


def freeze_model(pairs_path: Path, checkpoint: Path, output: Path) -> dict:
    pairs_path, checkpoint, output = (p.resolve() for p in (pairs_path, checkpoint, output))
    pairs = json.loads(pairs_path.read_text())
    report_path = checkpoint.parent/'result.json'
    report = json.loads(report_path.read_text())
    if (pairs.get('kind') != 'supervised-video-replay-pairs' or pairs.get('split') != 'train'
            or not pairs.get('training_ready') or report.get('pairs_sha256') != sha256(pairs_path)
            or report.get('context_frames') != pairs['context_frames']
            or report.get('image_post_phase_verified') is not True):
        raise ValueError('audited training pairs and matching trained checkpoint report required')
    players = {p['port']: p for p in pairs['settings']['players']}
    characters = [players[port]['character'] for port in pairs['ports']]
    result = {'schema': 1, 'kind': 'frozen-temporal-image-model',
        'checkpoint': os.path.relpath(checkpoint, output.parent), 'checkpoint_sha256': sha256(checkpoint),
        'training_pairs_sha256': sha256(pairs_path), 'training_report_sha256': sha256(report_path),
        'training_replay_sha256': pairs['replay_sha256'], 'stage': pairs['settings']['stage'],
        'slot_characters': characters, 'training_ports': pairs['ports'],
        'slot_mapping': 'unique external character ID -> supplied physical port; no image flip or label-optimized assignment',
        'context_frames': pairs['context_frames'], 'feature_size': 3072, 'hidden_size': 128,
        'encoder_weights_sha256': report['encoder_weights_sha256'],
        'torch_version': report['torch_version'], 'torchvision_version': report['torchvision_version'],
        'baseline_sha256': report['baseline_sha256'], 'training_script_sha256': report['script_sha256'],
        'encoder': report['encoder'], 'button_logit_threshold': 0,
        'policy': 'freeze before validation; scores are not calibrated probabilities; native VI/PAD adaptation unverified'}
    slot_ports(result, pairs['settings'])
    with output.open('x') as handle: handle.write(json.dumps(result, indent=2)+'\n')
    return result


def image_view(video_dir: Path, output: Path) -> dict:
    video_dir, output = video_dir.resolve(), output.resolve()
    video_path = video_dir/'ingested/video.json'
    provenance_path, index_path = video_dir/'source-provenance.json', video_dir/'capture-index.json'
    video, provenance, index = (json.loads(p.read_text()) for p in (video_path, provenance_path, index_path))
    if (provenance.get('passed') is not True or provenance.get('kind') not in (
            'supervised-replay-source-video', 'supplied-replay-source-video')
            or provenance['video_sha256'] != video['source_sha256']
            or sha256(video_dir/'source.mp4') != video['source_sha256']
            or not {sha256(video_path), sha256(index_path)} <= set(provenance['identities'].values())
            or len(index) != len(video['frames'])):
        raise ValueError('identity-bound prepared source video required')
    setup = provenance['supplied_setup']
    settings = {'stage': setup['stage'], 'players': [
        {name: p[name] for name in ('port', 'character', 'costume')} for p in setup['players']]}
    frames = []
    for i, (image, row) in enumerate(zip(video['frames'], index)):
        path = (video_dir/'ingested'/image['image']).resolve()
        if image['index'] != i or row['video_frame'] != i or sha256(path) != image['image_sha256']:
            raise ValueError('changed or miskeyed inference image')
        frames.append({name: image[name] for name in ('index', 'pts', 'relative_seconds', 'image_sha256')}
            | {'image': os.path.relpath(path, output.parent), 'replay_frame': row['replay_frame']})
    result = {'schema': 1, 'kind': 'image-only-known-roster-video',
        'replay_sha256': provenance['source_replay_sha256'], 'video_sha256': video['source_sha256'],
        'settings': settings, 'width': video['width'], 'height': video['height'],
        'time_base': video['time_base'], 'frames': frames,
        'identities': {'video_manifest': sha256(video_path), 'preparation': sha256(provenance_path)},
        'policy': 'model receives image pixels and known roster only; frame IDs/PTS are output keys, not network features; no original controls or later state'}
    validate_image_view(result, 3)
    with output.open('x') as handle: handle.write(json.dumps(result, indent=2)+'\n')
    return result
