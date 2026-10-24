"""Prepare official signed-frame video for training or frozen-model evaluation.

Training phase audits intentionally read controller/state labels; reference mode
transfers the training convention without exporting target controls. Both modes
compare original/official post state to validate capture. Inference receives none
of these labels or phase annotations.
"""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import tempfile

from yt2slp.benchmark import compare_posts
from yt2slp.frame_index import GEOMETRY, assess_step, cyan_cells, decode_index, verify_log_policy
from yt2slp.timer_labels import label_images, png_size, add_manual_readings
from yt2slp.training_phase import audit_phase, frozen_phase_reference, pipeline_phase_reference
from yt2slp.video import ingest_video, sha256
from yt2slp.footage import capture_request_start
from yt2slp.corpus import hud_check


def node(tool, *args):
    return json.loads(subprocess.check_output(['node', 'tools/slippi-parser/'+tool, *map(str, args)]))


def audit_capture(folder, replay, timer_calibration, hud_readings=None, hud_policy='strict'):
    capture = json.loads((folder/'capture.json').read_text())
    index = json.loads((folder/'capture-index.json').read_text())
    calibration = json.loads((folder/'osd-calibration.json').read_text())
    if (capture.get('kind') != 'official-stepped-frame-capture' or capture.get('capture_passed') is not True
            or capture.get('playback_version') != '3.5.2' or capture.get('should_resync') is not False
            or capture.get('source_replay_sha256') != sha256(replay)):
        raise ValueError('successful identity-bound official stepped capture required')
    first, last = capture['wanted_interval']
    if (capture['request_interval'] != [capture_request_start(first,last),last+3]
            or [r['replay_frame'] for r in index] != list(range(first, last+1))):
        raise ValueError('incomplete or unsupported signed capture interval')
    screens = sorted((folder/'screens').glob('*.png'))
    if [p.name for p in screens] != [f'{i:06d}.png' for i in range(len(screens))]:
        raise ValueError('missing retained UI screenshot')
    g = GEOMETRY; width = g['cells']*g['cell_width']; height = g['height']; size = width*height*3
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-start_number', '0', '-i', str(folder/'screens/%06d.png'),
        '-vf', f'crop={width}:{height}:{g["left"]}:{g["top"]},format=rgb24',
        '-fps_mode', 'passthrough', '-f', 'rawvideo', 'pipe:1'], timeout=120)
    if len(raw) != size*len(screens): raise ValueError('decoded UI strip count differs')
    rendered = {str(p.relative_to(folder)): decode_index(cyan_cells(raw[i*size:(i+1)*size], width, height, cropped=True), calibration)
                for i, p in enumerate(screens)}
    for anchor in calibration['sources']:
        image = folder/anchor['image']
        pixels = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(image), '-frames:v', '1',
            '-vf', f'crop={width}:{height}:{g["left"]}:{g["top"]},format=rgb24', '-f', 'rawvideo', 'pipe:1'])
        if sha256(image) != anchor['sha256'] or decode_index(cyan_cells(pixels, width, height, cropped=True), calibration) != anchor['frame']:
            raise ValueError('OSD calibration source identity or index differs')
    used = set()
    for row in index:
        frame = row['replay_frame']; image = folder/'user/Dump/Frames'/row['capture_image']
        if row['capture_image'] in used: raise ValueError('reused clean dump image')
        used.add(row['capture_image'])
        if (png_size(image) != [642, 528] or sha256(image) != row['capture_image_sha256']
                or sha256(folder/row['index_screen']) != row['index_screen_sha256']
                or sha256(folder/row['next_index_screen']) != row['next_index_screen_sha256']
                or rendered[row['index_screen']] != frame
                or rendered[row['next_index_screen']] != frame+1
                or row.get('dump_pipeline_delay_swaps') != 1):
            raise ValueError('clean PNG / retained OSD screenshot identity or index differs')
        verify_log_policy(row,capture)
        assess_step(frame, row['next_frame_osd'], row['next_frame_log'], [row['capture_image']],
                    paused_log_minus_osd=row['paused_log_minus_osd'])
    timers = node('export-timers.cjs', replay, last)
    timer_first = max(1,first)
    timer_labels = label_images(folder/'user/Dump/Frames', json.loads(timer_calibration.read_text()), timers, timer_first, last)
    if hud_readings:
        timer_labels = add_manual_readings(timer_labels,json.loads(hud_readings.read_text()),folder/'user/Dump/Frames',timers)
    hud = hud_check(index,timer_labels,hud_policy)
    if len(capture['regenerated_replays']) != 1: raise ValueError('one real regenerated replay required')
    state = compare_posts(node('export-state.cjs', replay),
        node('export-state.cjs', folder/capture['regenerated_replays'][0]), first, last)
    return capture, index, timers, {'schema': 1,
        'passed': hud['passed'] and state['passed'],
        'signed_interval': [first, last], 'hud_osd_disagreement_frames': hud['disagreement_frames'],
        'osd_verified_frames': len(index), 'positive_hud_crosschecked_frames': hud['compared'],
        'positive_hud_interval': [timer_first,last],
        'hud_corroboration':hud,
        'dump_pipeline_delay_swaps': 1, 'positive_timer_labels': timer_labels,
        'paused_log_association': capture.get('paused_log_association','fixed'),
        'source_original_vs_official': state,
        'policy': 'exact rendered OSD per paused frame plus fixed source-audited PBO delay; independent positive HUD crosscheck; no fitted frame offset'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('replay', 'capture', 'timer-calibration', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    phase_options = parser.add_mutually_exclusive_group(required=True)
    phase_options.add_argument('--phase-observations', type=Path)
    phase_options.add_argument('--phase-reference', type=Path,
        help='apply a frozen training phase convention; does not export validation controls for phase fitting')
    phase_options.add_argument('--pipeline-phase-reference',type=Path,help='explicit experimental same-pipeline phase transfer for the expanded roster')
    parser.add_argument('--hud-policy',choices=('strict','corpus-v1'),default='strict')
    parser.add_argument('--hud-readings',type=Path,help='literal image-bound visual readings for unknown HUD OCR results')
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    try:
        capture, index, timers, audit = audit_capture(args.capture, args.replay, args.timer_calibration,args.hud_readings,args.hud_policy)
        (out/'frame-labels.json').write_text(json.dumps(audit, indent=2)+'\n')
        if not audit['passed']:
            raise ValueError('independent positive HUD or original/official state check failed; see retained frame-labels.json')
        first, last = capture['wanted_interval']
        setup = node('inspect-settings.cjs', args.replay)['replays'][0]
        if args.phase_observations:
            labels = node('export-training.cjs', args.replay, first-2, last+2)
            observations = json.loads(args.phase_observations.read_text())
            if observations.get('capture_index_sha256') != sha256(args.capture/'capture-index.json'):
                raise ValueError('manual phase observations belong to another capture')
            phase = audit_phase(observations, labels, index)
            phase_inputs = [args.phase_observations]
        elif args.pipeline_phase_reference:
            phase = pipeline_phase_reference(args.pipeline_phase_reference,setup,sha256(args.replay))
            phase_inputs = [args.pipeline_phase_reference,args.pipeline_phase_reference.parent/'phase-audit.json',
                            args.pipeline_phase_reference.parent/'frame-labels.json']
        else:
            phase = frozen_phase_reference(args.phase_reference, setup, sha256(args.replay))
            phase_inputs = [args.phase_reference, args.phase_reference.parent/'phase-audit.json',
                            args.phase_reference.parent/'frame-labels.json']
        (out/'phase-audit.json').write_text(json.dumps(phase, indent=2)+'\n')
        if not phase['passed']: raise ValueError('predeclared zero image/post phase is unverified or ambiguous')
        mapping = [{**row, 'video_frame': i, 'literal_timer': timers[str(row['replay_frame'])] if row['replay_frame'] >= 0 else None}
                   for i, row in enumerate(index)]
        (out/'capture-index.json').write_text(json.dumps(mapping, indent=2)+'\n')
        with tempfile.TemporaryDirectory(dir=out) as temporary:
            for row in mapping:
                (Path(temporary)/f'{row["video_frame"]:06d}.png').symlink_to(
                    (args.capture/'user/Dump/Frames'/row['capture_image']).resolve())
            subprocess.run(['ffmpeg', '-v', 'error', '-framerate', '60', '-i', str(Path(temporary)/'%06d.png'),
                '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-pix_fmt', 'yuv420p', str(out/'source.mp4')],
                check=True, timeout=120)
        video = ingest_video(out/'source.mp4', out/'ingested')
        if (len(video['frames']) != len(mapping) or [video['width'], video['height']] != [642, 528]
                or any(Fraction(row['relative_seconds']) != Fraction(i, 60) for i, row in enumerate(video['frames']))):
            raise ValueError('encoding/decoding changed declared frame count, geometry or PTS')
        report = {'schema': 1, 'kind': 'supervised-replay-source-video', 'passed': True,
            'source_replay_sha256': sha256(args.replay), 'video_sha256': video['source_sha256'],
            'interval': [first, last], 'supplied_setup': setup,
            'frame_label_method': 'stepped signed OSD with independent positive HUD crosscheck',
            'original_controls_exported_for_phase_audit': args.phase_observations is not None,
            'original_post_state_used_for_playback_audit': True,
            'phase_method': phase['kind'],
            'native_setup_parity_validated': False,
            'policy': 'audited source preparation; phase method explicitly recorded; clean frames only, UI frame IDs never enter network features; native VI adapter remains separate',
            'identities': {str(p): sha256(p) for p in (Path(__file__), args.replay,
                args.capture/'capture.json', args.capture/'capture-index.json', args.capture/'osd-calibration.json',
                args.timer_calibration, *([args.hud_readings] if args.hud_readings else []), *phase_inputs, out/'frame-labels.json', out/'phase-audit.json',
                out/'capture-index.json', out/'ingested/video.json', Path('src/yt2slp/frame_index.py'),
                Path('src/yt2slp/training_phase.py'))}}
        (out/'source-provenance.json').write_text(json.dumps(report, indent=2)+'\n')
    except Exception as error:
        (out/'preparation-failure.json').write_text(json.dumps({'passed': False, 'error': str(error)}, indent=2)+'\n')
        raise
    print(out/'source.mp4')


if __name__ == '__main__': main()
