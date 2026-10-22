"""Compare selected native/official states and label a controlled reference clip.

Run in Docker. The timer calibration is local, manually verified evidence; it
must never be committed as a redistributed game font or inferred from file order.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from yt2slp.benchmark import compare_posts, observation_rows
from yt2slp.reference_cases import REFERENCE_CASES
from yt2slp.timer_labels import label_images


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_state(replay, output):
    with output.open('x') as handle:
        subprocess.run(['node','tools/slippi-parser/export-state.cjs',str(replay)],stdout=handle,check=True)
    return json.loads(output.read_text())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path)
    p.add_argument('--calibration',type=Path,required=True)
    a=p.parse_args();root=a.run.resolve()
    native_manifest=json.loads((root/'benchmark.json').read_text())
    capture=json.loads((root/'official/capture.json').read_text())
    if native_manifest['case'] not in REFERENCE_CASES or not capture['capture_passed']:
        raise ValueError('missing successful supported native/official case')
    first,last=native_manifest['clip']['first'],native_manifest['clip']['last']
    if [first,last]!=capture['wanted_interval'] or capture['should_resync'] is not False:
        raise ValueError('capture interval/resync policy differs from benchmark')
    if native_manifest['replay_sha256']!=sha256(root/'native.slp') or capture['source_replay_sha256']!=native_manifest['replay_sha256']:
        raise ValueError('capture is not bound to this native replay')
    iso_identity=native_manifest['identities']['/assets/melee.iso']
    if iso_identity not in capture['identities'].values():raise ValueError('native/official ISO identity mismatch')
    if len(capture['regenerated_replays'])!=1:raise ValueError('ambiguous regenerated replay selection')
    out=a.output.resolve() if a.output else root/'analysis';out.mkdir(exist_ok=False)
    reference=export_state(root/'native.slp',out/'native-state.json')
    regenerated=root/'official'/capture['regenerated_replays'][0]
    official=export_state(regenerated,out/'official-state.json')
    settings=reference['settings']
    if (settings['stage']!=31 or [p['character'] for p in settings['players']]!=[2,20]
            or settings['timer_type']!=2 or settings['timer_seconds']!=120):
        raise ValueError('timer alignment supports only the documented unpaused Fox/Falco Battlefield case')
    state=compare_posts(reference,official,first,last)
    observations=json.loads((root/'observations.json').read_text())
    observed={'schema':1,'rows':observation_rows(observations)}
    native_phase=compare_posts(reference,observed,first,last,
        fields=('action','stocks','animation','x','y','percent','facing'),compare_settings=False)
    calibration=json.loads(a.calibration.read_text())
    labels=label_images(root/'official/user/Dump/Frames',calibration,reference['timers'],first,last)
    (out/'frame-labels.json').write_text(json.dumps(labels,indent=2)+'\n')
    clip_info=None
    if labels['passed']:
        with (out/'frame-index.csv').open('w',newline='') as handle:
            writer=csv.writer(handle);writer.writerow(['clip_frame','game_frame','rendered_timer','captured_image'])
            for index,frame in enumerate(range(first,last+1)):
                writer.writerow([index,frame,reference['timers'][str(frame)],labels['selected'][frame]])
        with tempfile.TemporaryDirectory(dir=out) as temporary:
            inputs=Path(temporary)
            for index,frame in enumerate(range(first,last+1)):
                (inputs/f'{index:06d}.png').symlink_to(root/'official/user/Dump/Frames'/labels['selected'][frame])
            subprocess.run(['ffmpeg','-v','error','-framerate','60','-i',str(inputs/'%06d.png'),
                '-c:v','ffv1','-pix_fmt','bgra',str(out/'reference.mkv')],check=True)
        clip_info=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames',
            '-select_streams','v:0','-show_entries','stream=codec_name,width,height,nb_read_frames,r_frame_rate',
            '-of','json',str(out/'reference.mkv')],text=True))['streams'][0]
        if int(clip_info['nb_read_frames'])!=last-first+1 or clip_info['r_frame_rate']!='60/1':
            raise ValueError('generated reference clip frame count/rate mismatch')
    passed=state['passed'] and native_phase['passed'] and labels['passed']
    tools={name:subprocess.check_output(command,stderr=subprocess.STDOUT,text=True).splitlines()[0]
           for name,command in [('ffmpeg',['ffmpeg','-version']),('ffprobe',['ffprobe','-version']),('node',['node','--version'])]}
    report={'schema':1,'case':native_manifest['case'],'passed':passed,
        'native_vs_official_postframes':state,'native_observation_phase_check':native_phase,
        'frame_alignment':{k:v for k,v in labels.items() if k not in ('records','selected')},
        'reference_clip':clip_info,'calibration_sha256':sha256(a.calibration),
        'native_replay_sha256':reference['replay_sha256'],'official_replay_sha256':official['replay_sha256'],
        'identities':{str(path):sha256(path) for path in [Path(__file__),Path('src/yt2slp/benchmark.py'),Path('src/yt2slp/reference_cases.py'),
            Path('src/yt2slp/timer_labels.py'),Path('tools/slippi-parser/export-state.cjs'),
            Path('docker/Dockerfile'),Path('uv.lock'),Path('tools/slippi-parser/package-lock.json'),a.calibration,
            root/'benchmark.json',root/'observations.json',root/'inputs.txt',root/'official/capture.json',
            root/'official/request.json',root/'official/stdout.log',
            root/'official/user/Config/Dolphin.ini',root/'official/user/Config/GFX.ini',
            root/'official/user/GameSettings/GALE01r2.ini',out/'native-state.json',out/'official-state.json',
            out/'frame-labels.json']},
        'tool_versions':tools,'full_state_equality_measured':False,'native_image_equality_measured':False,
        'render_vs_post_update_phase_equality_established':False,
        'reconstruction_accuracy_thresholds_established':False}
    if clip_info:report['reference_clip_sha256']=sha256(out/'reference.mkv')
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
