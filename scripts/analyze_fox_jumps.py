"""Verify actual official playback of the 2/3-request boundary and compare images.

Run in Docker after host capture. Short hop is left, full hop right. Frame
labels come from the existing rendered timer calibration, never PNG order.
"""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import tempfile

from yt2slp.benchmark import compare_posts, index_rows, observation_rows
from yt2slp.timer_labels import label_images
from yt2slp.video import sha256
from analyze_benchmark import export_state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--measurements',type=Path,required=True)
    parser.add_argument('--calibration',type=Path,required=True)
    args=parser.parse_args()
    root=args.measurements.resolve()
    measured=json.loads((root/'measurements.json').read_text())
    if measured.get('kind')!='fox-short-full-hop-boundary' or not measured['passed']:
        raise ValueError('missing successful jump-boundary measurement')
    out=root/'official-analysis';out.mkdir(exist_ok=False)
    checks={};selections={};states={}
    identities={str(p):sha256(p) for p in (Path(__file__),root/'measurements.json',args.calibration,
        Path('scripts/analyze_benchmark.py'),Path('src/yt2slp/benchmark.py'),Path('src/yt2slp/timer_labels.py'),
        Path('tools/slippi-parser/export-state.cjs'),Path('tools/slippi-parser/package-lock.json'))}
    try:
        for held,name in ((2,'short'),(3,'full')):
            result=next(r for r in measured['results'] if r['held_requests']==held and r['button']=='X')
            replay=root/result['replay']
            official=replay.parent/'official'
            capture=json.loads((official/'capture.json').read_text())
            if (sha256(replay)!=result['replay_sha256'] or not capture['capture_passed']
                    or capture['playback_version']!='3.5.2' or capture['should_resync'] is not False
                    or capture['source_replay_sha256']!=result['replay_sha256']
                    or capture['wanted_interval']!=[240,300] or len(capture['regenerated_replays'])!=1
                    or measured['identities']['/assets/melee.iso'] not in capture['identities'].values()):
                raise ValueError('official capture is not bound to the declared measured jump')
            native=export_state(replay,out/f'{name}-native.json')
            regenerated=official/capture['regenerated_replays'][0]
            actual=export_state(regenerated,out/f'{name}-official.json')
            field_check=compare_posts(native,actual,240,300)
            observed={'schema':1,'rows':observation_rows(json.loads((replay.parent/'observations.json').read_text()))}
            phase=compare_posts(native,observed,240,300,
                fields=('action','stocks','animation','x','y','percent','facing'),compare_settings=False)
            labels=label_images(official/'user/Dump/Frames',json.loads(args.calibration.read_text()),native['timers'],240,300)
            (out/f'{name}-labels.json').write_text(json.dumps(labels,indent=2)+'\n')
            checks[name]={'held_requests':held,'native_vs_official':field_check,'observation_phase':phase,
                'rendered_timer_coverage':labels['passed'],'measured':result}
            states[name]=index_rows(native)
            selections[name]={frame:official/'user/Dump/Frames'/labels['selected'][frame] for frame in range(240,301)} if labels['passed'] else {}
            identities.update({str(p):sha256(p) for p in (official/'capture.json',replay,regenerated,
                out/f'{name}-native.json',out/f'{name}-official.json',out/f'{name}-labels.json')})
        passed=all(c['native_vs_official']['passed'] and c['observation_phase']['passed'] and c['rendered_timer_coverage'] for c in checks.values())
        first_y_difference=next((frame for frame in range(240,301) if states['short'][(frame,0)]['y']!=states['full'][(frame,0)]['y']),None)
        if passed:
            with tempfile.TemporaryDirectory(dir=out) as temporary:
                images=Path(temporary)
                for name in ('short','full'):
                    (images/name).mkdir()
                    for i,frame in enumerate(range(240,301)):
                        (images/name/f'{i:06d}.png').symlink_to(selections[name][frame])
                subprocess.run(['ffmpeg','-v','error','-framerate','60','-i',str(images/'short/%06d.png'),
                    '-framerate','60','-i',str(images/'full/%06d.png'),'-filter_complex','hstack=inputs=2',
                    '-c:v','ffv1',str(out/'comparison.mkv')],check=True)
            with (out/'comparison-index.csv').open('w',newline='') as handle:
                writer=csv.writer(handle);writer.writerow(['clip_index','game_frame','short_png','full_png'])
                for i,frame in enumerate(range(240,301)):
                    writer.writerow([i,frame,str(selections['short'][frame]),str(selections['full'][frame])])
        report={'schema':1,'passed':passed,'cases':checks,'first_y_difference_frame':first_y_difference,
            'identities':identities,'comparison':'short hop left, full hop right; game frames 240..300',
            'native_vertical_velocity_compared_to_official':False,'full_state_equality_measured':False}
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'passed':passed,'first_y_difference_frame':first_y_difference,'comparison':str(out/'comparison.mkv')},indent=2))
        return 0 if passed else 1
    except Exception as exc:
        (out/'analysis-failure.json').write_text(json.dumps({'error':str(exc),'completed':checks},indent=2)+'\n')
        raise


if __name__=='__main__':
    raise SystemExit(main())
