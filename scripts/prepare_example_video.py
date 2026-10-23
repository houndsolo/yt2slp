"""Make a timer-labelled MP4 from an actual supplied replay's official capture.

Source controls and later posts are not read. Setup/codes remain explicit
preparation evidence, separate from the ingested reconstruction input.
"""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import tempfile

from yt2slp.timer_labels import label_images
from yt2slp.video import ingest_video, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('replay', 'settings', 'capture', 'calibration', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    source = args.replay.resolve()
    setup = json.loads(args.settings.read_text())['replays']
    capture = json.loads((args.capture/'capture.json').read_text())
    if (len(setup) != 1 or setup[0]['replay_sha256'] != sha256(source)
            or not capture['capture_passed'] or capture['should_resync'] is not False
            or capture['source_replay_sha256'] != sha256(source)
            or capture['playback_version'] != '3.5.2' or capture['request_interval'][0] != -123):
        raise ValueError('identity-bound supplied setup and full Ready official capture required')
    first, last = capture['wanted_interval']
    if not 1 <= first <= last <= 1800:raise ValueError('supported positive countdown interval required')
    out = args.output.resolve();out.mkdir(parents=True, exist_ok=False)
    try:
        timers = json.loads(subprocess.check_output(['node', 'tools/slippi-parser/export-timers.cjs', str(source), str(last)]))
        labels = label_images(args.capture/'user/Dump/Frames', json.loads(args.calibration.read_text()), timers, first, last)
        (out/'frame-labels.json').write_text(json.dumps(labels, indent=2)+'\n')
        if not labels['passed']:raise ValueError('source capture lacks complete unique timer labels; no MP4 published')
        mapping = [{'video_frame': i, 'replay_frame': frame, 'literal_timer': timers[str(frame)],
            'capture_image': labels['selected'][frame],
            'capture_image_sha256': sha256(args.capture/'user/Dump/Frames'/labels['selected'][frame])}
            for i, frame in enumerate(range(first,last+1))]
        (out/'capture-index.json').write_text(json.dumps(mapping, indent=2)+'\n')
        with tempfile.TemporaryDirectory(dir=out) as temporary:
            frames = Path(temporary)
            for row in mapping:
                (frames/f"{row['video_frame']:06d}.png").symlink_to((args.capture/'user/Dump/Frames'/row['capture_image']).resolve())
            subprocess.run(['ffmpeg','-v','error','-framerate','60','-i',str(frames/'%06d.png'),
                '-c:v','libx264','-crf','18','-preset','medium','-pix_fmt','yuv420p',str(out/'source.mp4')], check=True, timeout=120)
        video = ingest_video(out/'source.mp4', out/'ingested')
        if (len(video['frames']) != last-first+1 or [video['width'],video['height']] != [642,528]
                or any(Fraction(r['relative_seconds']) != Fraction(i,60) for i,r in enumerate(video['frames']))):
            raise ValueError('source transcode changed declared geometry/count/timestamps')
        report = {'schema':1,'kind':'supplied-replay-source-video','passed':True,
            'source_replay_sha256':sha256(source),'video_sha256':video['source_sha256'],
            'interval':[first,last], 'supplied_setup':setup[0],
            'source_controls_used_for_selection':False,'later_source_state_used_for_selection':False,
            'native_setup_parity_validated':False,
            'policy':'official rendering of an actual example; reconstruction receives MP4/manual observations and declared setup, not source controllers/later posts',
            'identities':{str(p):sha256(p) for p in (Path(__file__),source,args.settings,
                args.capture/'capture.json',args.calibration,out/'frame-labels.json',out/'capture-index.json',
                out/'ingested/video.json',Path('tools/slippi-parser/export-timers.cjs'),Path('src/yt2slp/timer_labels.py'))}}
        (out/'source-provenance.json').write_text(json.dumps(report, indent=2)+'\n')
    except Exception as exc:
        (out/'preparation-failure.json').write_text(json.dumps({'error':str(exc),'passed':False}, indent=2)+'\n')
        raise
    print(out/'source.mp4')


if __name__ == '__main__':main()
