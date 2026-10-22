#!/usr/bin/env python3
"""Capture official Slippi Playback PNGs and regenerated game events on the host.

Run under xvfb-run or a desktop. Frame labels are verified later from the HUD;
PNG numbers and movie timestamps are never assumed to be replay frame numbers.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def assess_window(text, start, end, replay):
    frames = [int(n) for n in re.findall(r'^\[CURRENT_FRAME\] (-?\d+)$',text,re.M)]
    paths = re.findall(r'^\[FILE_PATH\] (.+)$',text,re.M)
    return bool(frames and frames[0] == start and frames[-1] >= end
                and all(b==a+1 for a,b in zip(frames,frames[1:]))
                and paths and all(p == str(replay) for p in paths))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dolphin',type=Path,default=os.environ.get('YT2SLP_DOLPHIN'))
    p.add_argument('--iso',type=Path,default=os.environ.get('YT2SLP_ISO'))
    p.add_argument('--replay',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--first',type=int,default=240)
    p.add_argument('--last',type=int,default=300)
    p.add_argument('--padding',type=int,default=20)
    p.add_argument('--timeout',type=float,default=120)
    args=p.parse_args()
    if args.first <= args.padding or args.padding < 1 or args.last < args.first or not 0 < args.timeout < 3600:
        p.error('invalid supported capture interval/budget')
    for path in (args.dolphin,args.iso,args.replay):
        if path is None or not path.is_file(): p.error(f'missing input: {path}')
    exe,iso,replay=(path.resolve() for path in (args.dolphin,args.iso,args.replay))
    version=subprocess.run([str(exe),'--version'],capture_output=True,text=True,timeout=20)
    if version.stdout.strip() != '3.5.2':
        p.error('capture settings and timer alignment are validated only for Playback 3.5.2')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    user=out/'user';(user/'Config').mkdir(parents=True);(user/'Dump/Frames').mkdir(parents=True)
    (user/'GameSettings').mkdir()
    (user/'GameSettings/GALE01r2.ini').write_text('[Gecko_Enabled]\n$Required: General Codes\n$Required: Slippi Playback\n$Recommended: Slippi Recording\n')
    (user/'Config/Dolphin.ini').write_text(
        '[Core]\nCPUThread = False\nDSPHLE = True\nGFXBackend = OGL\n'
        f'SlippiRegenerateReplays = True\nSlippiReplayRegenerateDir = {out / "regenerated"}\n'
        '[Interface]\nConfirmStop = False\n[Movie]\nDumpFrames = True\nDumpFramesSilent = True\n'
        '[DSP]\nBackend = No audio output\n')
    (user/'Config/GFX.ini').write_text('[Hardware]\nVSync = False\n[Settings]\nDumpFramesAsImages = True\nEFBScale = 2\nInternalResolutionFrameDumps = True\nShowFPS = False\n')
    start,end=args.first-args.padding-1,args.last+args.padding+1
    request=out/'request.json'
    request.write_text(json.dumps({'mode':'normal','replay':str(replay),'commandId':'yt2slp-reference-v1',
        'startFrame':start,'endFrame':end,'shouldResync':False,'rollbackDisplayMethod':'off'},indent=2)+'\n')
    command=[str(exe),'--exec='+str(iso),'--slippi-input='+str(request),'--user='+str(user),'--batch','--cout']
    text=''
    with (out/'stdout.log').open('wb') as log:
        proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            deadline=time.monotonic()+args.timeout
            while time.monotonic()<deadline:
                text=(out/'stdout.log').read_text(errors='replace')
                if assess_window(text,start,end,replay):
                    time.sleep(1) # Drain final recording/image work; captured menu images stay unlabelled.
                    break
                if proc.poll() is not None: break
                time.sleep(.25)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    text=(out/'stdout.log').read_text(errors='replace')
    files=sorted((out/'regenerated').glob('*.slp'))
    images=list((user/'Dump/Frames').glob('framedump_*.png'))
    passed=assess_window(text,start,end,replay) and len(files)==1 and bool(images)
    identities={str(path):sha256(path) for path in (exe,iso,replay,Path(__file__))}
    wrapped=exe.parent/'AppRun.wrapped'
    if wrapped.is_file(): identities[str(wrapped.resolve())]=sha256(wrapped.resolve())
    sys=exe.parent/'usr/bin/Sys'
    if sys.is_dir():
        h=hashlib.sha256()
        for path in sorted(sys.rglob('*')):
            if path.is_file(): h.update(str(path.relative_to(sys)).encode()+b'\0'+bytes.fromhex(sha256(path)))
        identities['packaged_sys_tree']=h.hexdigest()
    result={'schema':1,'playback_version':'3.5.2','source_tag':'project-slippi/Ishiiruka@v3.5.2',
        'source_commit':'bffe989d0bd3b83a4be3eaee708cf2755659e01e','identities':identities,
        'command':command,'source_replay_sha256':sha256(replay),'request_interval':[start,end],
        'wanted_interval':[args.first,args.last],'captured_png_count':len(images),
        'regenerated_replays':[str(path.relative_to(out)) for path in files],
        'capture_passed':passed,'frame_alignment_verified':False,'state_comparison_passed':None,
        'should_resync':False,'image_equality_measured':False}
    (out/'capture.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
