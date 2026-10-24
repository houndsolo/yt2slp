"""Render frozen train/validation clips locally for transfer to the V100.

Requires the host's official Playback/X11 tools. Audits, encoding and label
exports run in the project Docker environment. Resumes successful clips;
publishes a complete manifest only after every selected clip passes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from yt2slp.footage import select_footage
from yt2slp.video import sha256

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n')
    temporary.replace(path)


def command(args, log, output=None):
    with log.open('a') as handle:
        handle.write('\nCOMMAND '+repr(list(map(str,args)))+'\n'); handle.flush()
        if output is None:
            subprocess.run(list(map(str,args)), cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, check=True)
        else:
            with output.open('x') as destination:
                subprocess.run(list(map(str,args)), cwd=ROOT, stdout=destination, stderr=handle, check=True)


def prepare_one(match, out, args):
    directory = out/'clips'/match['replay_sha256']; directory.mkdir(parents=True, exist_ok=True)
    receipt = directory/'clip.json'
    if receipt.exists():
        info = json.loads(receipt.read_text())
        if (any(info[k]!=match[k] for k in ('replay_sha256','file','group','split','interval'))
                or any(sha256(out/p)!=digest for p,digest in info['identities'].items())):
            raise ValueError('completed footage changed; preserve it and use a new output directory')
        return info
    replay = ROOT/match['file']
    if not replay.is_file(): raise ValueError('source replay missing: '+match['file'])
    if sha256(replay)!=match['replay_sha256']: raise ValueError('source replay changed')
    attempt = directory/f'attempt-{time.time_ns()}'; attempt.mkdir()
    log = attempt/'preparation.log'; video = attempt/'video'; labels = attempt/'labels.json'
    first,last = match['interval']
    docker = ['bash','scripts/docker.sh','run']
    known = {'c13e36c0f079200b6f00e2b3bef22ffe1165cde23797325218509718d794b40f':'learning-timing-v1/video-v2',
             '35f1c56f2c5ac6ceeb74ff5144d923443bf34251d4404802408c28e577a48ae7':'learning-heldout-v1/video'}
    try:
        if match['reuse_pilot']:
            shutil.copytree(ROOT/'.docker-state/local'/known[match['replay_sha256']], video)
        else:
            capture = attempt/'capture'
            reusable = []
            for path in sorted(directory.glob('attempt-*/capture/capture.json')):
                old = json.loads(path.read_text())
                if (old.get('capture_passed') is True and old.get('source_replay_sha256')==match['replay_sha256']
                        and old.get('wanted_interval')==match['interval']):
                    index = json.loads((path.parent/'capture-index.json').read_text())
                    if all(sha256(path.parent/'user/Dump/Frames'/r['capture_image'])==r['capture_image_sha256'] for r in index):
                        reusable.append(path.parent)
            if reusable:
                capture = reusable[-1]
                write_json(attempt/'capture-reference.json',{'capture':str(capture.relative_to(out)),
                    'receipt_sha256':sha256(capture/'capture.json'),'policy':'reuse successful capture; rerun preparation audits'})
            else:
                command(['xvfb-run','-a','-s','-screen 0 1024x768x24',sys.executable,'scripts/capture_signed_frames.py',
                    '--dolphin',args.dolphin,'--iso',args.iso,'--replay',replay,
                    '--osd-calibration',args.osd_calibration,'--first',first,'--last',last,
                    '--per-step-log-association','--timeout',1200,'--output',capture], log)
            prepare = docker+['python','scripts/prepare_signed_video.py','--replay',match['file'],
                '--capture',capture.relative_to(ROOT),'--timer-calibration',args.timer_calibration.relative_to(ROOT),
                '--phase-reference',args.phase_reference.relative_to(ROOT),'--output',video.relative_to(ROOT)]
            readings = out/'manual-readings'/f'{match["replay_sha256"]}.json'
            if readings.exists(): prepare += ['--hud-readings',readings.relative_to(ROOT)]
            command(prepare,log)
        command(docker+['node','tools/slippi-parser/export-training.cjs',match['file'],first,last], log, labels)
        provenance = json.loads((video/'source-provenance.json').read_text())
        targets = json.loads(labels.read_text())
        if (provenance.get('passed') is not True or provenance['interval']!=match['interval']
                or provenance['source_replay_sha256']!=match['replay_sha256']
                or targets['replay_sha256']!=match['replay_sha256'] or targets['interval']!=match['interval']):
            raise ValueError('prepared video/labels differ from frozen source interval')
        bound = [video/'source.mp4',video/'source-provenance.json',video/'capture-index.json',
                 video/'frame-labels.json',video/'phase-audit.json',video/'ingested/video.json',labels]
        info = {k:match[k] for k in ('replay_sha256','file','group','split','interval')}
        info.update(video=str(video.relative_to(out)),labels=str(labels.relative_to(out)),
            frames=last-first+1,identities={str(p.relative_to(out)):sha256(p) for p in bound})
        write_json(receipt,info)
        return info
    except Exception as error:
        write_json(attempt/'failure.json',{'passed':False,'error':str(error)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--plan',type=Path,default=ROOT/'configs/learning-corpus-split-v1.json')
    parser.add_argument('--dolphin',type=Path,default=ROOT/'.local/playback-inspect/squashfs-root/AppRun')
    parser.add_argument('--iso',type=Path,default=os.environ.get('YT2SLP_ISO'))
    parser.add_argument('--osd-calibration',type=Path,default=ROOT/'.docker-state/local/learning-timing-v1/osd-calibration.json')
    parser.add_argument('--timer-calibration',type=Path,default=ROOT/'.docker-state/local/vision-timer-calibration-v2/timer-calibration-local.json')
    parser.add_argument('--phase-reference',type=Path,default=ROOT/'.docker-state/local/learning-timing-v1/video-v2/source-provenance.json')
    parser.add_argument('--jobs',type=int,default=2)
    args = parser.parse_args()
    if args.iso is None or not 1<=args.jobs<=4: parser.error('ISO and 1..4 workers required')
    for key in ('output','plan','dolphin','iso','osd_calibration','timer_calibration','phase_reference'):
        setattr(args,key,getattr(args,key).resolve())
    if not args.output.is_relative_to(ROOT): parser.error('output must stay inside checkout')
    plan = json.loads(args.plan.read_text()); matches = select_footage(plan)
    out = args.output; out.mkdir(parents=True,exist_ok=True)
    selection = {'schema':1,'kind':'frozen-training-footage-selection','plan_sha256':sha256(args.plan),
        'frames_per_new_clip':600,'matches':matches,'test_matches_selected':0}
    selected = out/'selection.json'
    if selected.exists() and json.loads(selected.read_text())!=selection:
        raise ValueError('frozen selection differs; use a new output directory')
    write_json(selected,selection)
    status = out/'status.json'; completed = []; failures = []
    write_json(status,{'state':'preparing','completed':0,'total':len(matches)})
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        pending = {pool.submit(prepare_one,m,out,args):m for m in matches}
        for future in as_completed(pending):
            match = pending[future]
            try:
                completed.append(future.result()); print('Ready: '+match['file'],flush=True)
            except Exception as error:
                failures.append({'file':match['file'],'error':str(error)})
                print('Failed: '+match['file']+': '+str(error),flush=True)
            write_json(status,{'state':'preparing','completed':len(completed),'failed':failures,'total':len(matches)})
    if failures:
        write_json(status,{'state':'incomplete','completed':len(completed),'failed':failures,'total':len(matches)})
        return 1
    manifest = {'schema':1,'kind':'prepared-training-footage','selection':'selection.json',
        'selection_sha256':sha256(selected),'split_plan':os.path.relpath(args.plan,out),
        'split_plan_sha256':sha256(args.plan),'clips':sorted(completed,key=lambda c:c['replay_sha256']),
        'test_matches_opened':0,'phase_policy':'audited original pilots; same-pipeline zero-phase reference for new clips'}
    write_json(out/'footage.json',manifest)
    write_json(status,{'state':'ready','completed':len(completed),'frames':sum(c['frames'] for c in completed),'test_matches_opened':0})
    return 0


if __name__=='__main__': raise SystemExit(main())
