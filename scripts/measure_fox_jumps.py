"""Measure Fox's short/full-hop boundary from genuine native controller branches.

Run in Docker with the local ISO. This is a controlled mechanics experiment,
not an observation inferred from pixels or a reconstruction accuracy claim.
"""
import argparse
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import subprocess

from yt2slp.backend import NativeLinuxBackend, RunConfig, decode_float_bits
from yt2slp.match import MatchConfig
from yt2slp.search import PadPhase, PadSequence, run_schedule, schedule_document
from yt2slp.video import sha256
from reconstruct_manual import advance_to


def jump_metrics(trace):
    """Measure one uninterrupted ground jump; don't infer height from screen pixels."""
    if (not trace or any(o.scene_major != 2 or o.scene != 2 or not o.fighters[0][0] for o in trace)
            or any(b.match_frame != a.match_frame + 1 for a, b in zip(trace, trace[1:]))):
        raise ValueError("expected contiguous supported VS observations")
    if any(not math.isfinite(decode_float_bits(o.fighters[0][i])) for o in trace for i in (5,8)):
        raise ValueError("non-finite jump coordinate/velocity")
    squat = [i for i, o in enumerate(trace) if o.fighters[0][2] == 24]
    if not squat or squat != list(range(squat[0], squat[-1]+1)):
        raise ValueError("expected one contiguous jump squat")
    launch = squat[-1]+1
    if launch >= len(trace) or trace[launch].fighters[0][2] not in (25, 26):
        raise ValueError("missing ground-jump takeoff")
    landing = next((i for i in range(launch+1, len(trace)) if trace[i].fighters[0][2] == 42), None)
    if landing is None or trace[-1].fighters[0][2] != 14:
        raise ValueError("jump/landing/return to idle not fully observed")
    if any(o.fighters[0][2] not in (25, 26, 29, 30, 31) for o in trace[launch:landing]):
        raise ValueError("air jump, attack or other interrupt is outside this experiment")
    baseline = decode_float_bits(trace[squat[0]].fighters[0][5])
    apex = max(range(launch, landing), key=lambda i: decode_float_bits(trace[i].fighters[0][5]))
    return {"squat_first_frame":trace[squat[0]].match_frame,"squat_last_frame":trace[squat[-1]].match_frame,
            "jump_squat_frames":len(squat),"takeoff_frame":trace[launch].match_frame,
            "initial_native_vertical_velocity":decode_float_bits(trace[launch].fighters[0][8]),
            "apex_frame":trace[apex].match_frame,"baseline_y":baseline,
            "height_above_baseline":decode_float_bits(trace[apex].fighters[0][5])-baseline,
            "landing_frame":trace[landing].match_frame,
            "airborne_frames":trace[landing].match_frame-trace[launch].match_frame,
            "policy":"native game coordinates and declared action IDs; no camera fit or time offset"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    config=RunConfig(Path('build/headless/melee_headless'),Path('build/game/melee_game.so'),
        Path(os.environ.get('YT2SLP_ISO','/assets/melee.iso')),Path('.local/runs'),match=MatchConfig())
    boot=Path('third_party/melee-unlocked/port/scripts/native_vs.txt')
    results=[]
    signatures=[]
    try:
        with NativeLinuxBackend() as backend:
            backend.initialize(config)
            backend.start(boot,timeout=180)
            advance_to(backend,239)
            checkpoint=backend.capture()
            for held in (1,2,3,4,8):
                for button,name in ((0x400,'X'),(0x800,'Y')):
                    backend.restore(checkpoint)
                    schedule=PadSequence((PadPhase(6,0,0,button),PadPhase(6+held,0,0,0)))
                    trace=run_schedule(backend,schedule,122)
                    directory=out/f'hold-{held:02d}-{name}'
                    directory.mkdir()
                    replay=directory/'native.slp'
                    backend.record(replay)
                    (directory/'observations.json').write_text(json.dumps([asdict(o) for o in trace])+'\n')
                    with (directory/'parser-result.json').open('x') as handle:
                        subprocess.run(['node','tools/slippi-parser/validate.cjs',str(replay),'--last-frame','361'],stdout=handle,check=True)
                    metrics=jump_metrics(trace)
                    results.append({'held_requests':held,'button':name,'schedule':schedule_document(schedule),
                        'replay':str(replay.relative_to(out)),'replay_sha256':sha256(replay),**metrics})
                    signatures.append(tuple(o.fighters[0] for o in trace))
            # A fresh 3-request run checks the boundary's recording isn't polluted by other branches.
            with NativeLinuxBackend() as fresh:
                fresh.initialize(config);fresh.start(boot,timeout=180);advance_to(fresh,239)
                run_schedule(fresh,PadSequence((PadPhase(6,0,0,0x400),PadPhase(9,0,0,0))),122)
                fresh.record(out/'fresh-three-request.slp')
            if sha256(out/'fresh-three-request.slp')!=results[4]['replay_sha256']:
                raise ValueError("fresh boundary recording differs from restored branch")
        if (not all(r['jump_squat_frames']==3 for r in results)
                or not all(signatures[i]==signatures[0] for i in range(4))
                or not all(signatures[i]==signatures[4] for i in range(4,10))
                or signatures[0]==signatures[4]
                or results[0]['height_above_baseline']>=results[4]['height_above_baseline']):
            raise ValueError("measured branches do not establish the declared two-class jump boundary")
        report={'schema':1,'kind':'fox-short-full-hop-boundary','passed':True,'results':results,
            'measured_short_hold_requests':[1,2],'measured_full_hold_requests':[3,4,8],
            'fresh_three_request_recording_matches':True,'checkpoint_frame':239,'end_frame':361,
            'native_run':str(backend.last_run_dir),
            'official_playback_validated':False,'reconstruction_case':False,
            'identities':{str(p):sha256(p) for p in (Path(__file__),boot,config.iso,config.host,config.game_library,
                Path('src/yt2slp/search.py'),Path('tools/slippi-parser/validate.cjs'),Path('tools/slippi-parser/package-lock.json'))}}
        (out/'measurements.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'output':str(out),'short':results[0],'full':results[4]},indent=2))
    except Exception as exc:
        (out/'measurement-failure.json').write_text(json.dumps({'error':str(exc),'completed':results},indent=2)+'\n')
        raise


if __name__=='__main__':
    main()
