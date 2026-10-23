"""Validate native setup/controls for the tournament clip; this is not reconstruction.

Run record/verify in Docker, and official capture on the host between them.
The chosen seed and test controls are declared hypotheses, not video recovery.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess

from yt2slp.backend import NativeLinuxBackend, RunConfig
from yt2slp.benchmark import compare_posts, observation_rows
from yt2slp.match import MatchConfig, PlayerConfig, StockRules, PadInput
from yt2slp.video import sha256

BOOT=Path('third_party/melee-unlocked/port/scripts/native_vs.txt')
MATCH=MatchConfig(8,(PlayerConfig(20),PlayerConfig(0)),ports=(1,2),stock_rules=StockRules(480,4))


def read(path):return json.loads(path.read_text())


def continuation(backend, neutral=False):
    result=[]
    for index in range(180):
        pads=list(MATCH.neutral_pads())
        if not neutral:
            pads[1]=PadInput(button=0x400 if 6<=index<8 else 0)
            pads[2]=PadInput(stick_x=-80 if index<20 else 0)
        result.append(backend.step(tuple(pads)))
    return tuple(result)


def warmup(backend):
    while backend.observe().match_frame<241:
        previous=backend.observe().match_frame
        if backend.step(MATCH.neutral_pads()).match_frame!=previous+1:
            raise ValueError('probe requires one game frame per retrace')


def record(a):
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    config=RunConfig(Path('build/headless/melee_headless'),Path('build/game/melee_game.so'),
        Path(os.environ.get('YT2SLP_ISO','/assets/melee.iso')),Path('.local/runs'),match=MATCH)
    report={'schema':1,'kind':'tournament-start-control-probe','passed':False,
        'requested_match':asdict(MATCH),'seed':1,'time_base':0,'source_inputs_recovered':False,
        'source_game_state_compared':False,'reconstruction_attempted':False,'full_state_equality_measured':False}
    try:
        with NativeLinuxBackend() as backend:
            backend.initialize(config);initial=backend.start(BOOT,timeout=180)
            warmup(backend);captured=backend.observe();handle=backend.capture()
            first=continuation(backend);backend.record(out/'original.slp')
            backend.restore(handle)
            report['restored_pause_stable']=backend.observe()==captured
            repeated=continuation(backend);backend.record(out/'repeated.slp')
            backend.restore(handle)
            neutral=continuation(backend,True);backend.record(out/'neutral.slp')
            backend.restore(handle)
            selected=continuation(backend);backend.record(out/'selected.slp')
            trace=backend.observations
            (out/'observations.json').write_text(json.dumps([asdict(o) for o in trace])+'\n')
            report.update(native_run=str(backend.last_run_dir),initial_frame=initial.match_frame,
                checkpoint_frame=captured.match_frame,last_frame=backend.recording_status().last_frame,
                ended=backend.recording_status().ended,same_continuations=first==repeated==selected,
                both_player_inputs_observable={str(port):any(x.fighters[port]!=y.fighters[port] for x,y in zip(first,neutral)) for port in MATCH.ports})
        with NativeLinuxBackend() as fresh:
            fresh.initialize(config);fresh.start(BOOT,timeout=180);warmup(fresh)
            continuation(fresh);fresh.record(out/'fresh.slp')
            report['fresh_observations_match']=fresh.observations==trace
        hashes={name:sha256(out/f'{name}.slp') for name in ('original','repeated','neutral','selected','fresh')}
        report['replay_hashes']=hashes
        report['selected_bytes_reproduce']=len({hashes[k] for k in ('original','repeated','selected','fresh')})==1
        report['discarded_branch_differs']=hashes['neutral']!=hashes['selected']
        with (out/'parser-result.json').open('x') as handle:
            subprocess.run(['node','tools/slippi-parser/validate.cjs',str(out/'selected.slp'),'--last-frame','421'],check=True,stdout=handle)
        parsed=read(out/'parser-result.json');settings=parsed['settings']
        report['settings_checked']=(settings['stageId']==8 and settings['startingTimerSeconds']==480
            and not settings['isTeams'] and [(p['playerIndex'],p['characterId'],p['startStocks']) for p in settings['players']]==[(1,20,4),(2,0,4)])
        report['parser_validated']=parsed['replaySha256']==hashes['selected'] and parsed['gameEnd'] is None
        report['identities']={str(p):sha256(p) for p in (Path(__file__),config.host,config.game_library,config.iso,BOOT,out/'observations.json',out/'parser-result.json')}
        report['passed']=(report['last_frame']==421 and not report['ended'] and report['restored_pause_stable']
            and report['same_continuations'] and all(report['both_player_inputs_observable'].values())
            and report['fresh_observations_match'] and report['selected_bytes_reproduce']
            and report['discarded_branch_differs'] and report['settings_checked'] and report['parser_validated'])
        if not report['passed']:raise ValueError('native setup/control probe failed')
    except Exception as exc:
        report['error']=str(exc)
        (out/'probe-result.json').write_text(json.dumps(report,indent=2)+'\n')
        raise
    (out/'probe-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


def export(replay, output):
    with output.open('x') as handle:
        subprocess.run(['node','tools/slippi-parser/export-state.cjs',str(replay)],stdout=handle,check=True)
    return read(output)


def verify(a):
    root=a.run.resolve();prior=read(root/'probe-result.json');capture=read(root/'official/capture.json')
    replay=root/'selected.slp'
    if (not prior['passed'] or not prior['parser_validated'] or not capture['capture_passed']
            or capture['should_resync'] is not False or capture['wanted_interval']!=[1,421]
            or sha256(replay)!=prior['replay_hashes']['selected']
            or capture['source_replay_sha256']!=sha256(replay) or len(capture['regenerated_replays'])!=1
            or prior['identities']['/assets/melee.iso'] not in capture['identities'].values()):
        raise ValueError('probe lacks bound native/parser/actual official capture checks')
    out=root/'official-analysis';out.mkdir(exist_ok=False)
    native=export(replay,out/'native-state.json')
    official=export(root/'official'/capture['regenerated_replays'][0],out/'official-state.json')
    states=compare_posts(native,official,1,421,player_indices=MATCH.ports)
    observations=observation_rows(read(root/'observations.json'),MATCH.ports)
    phase=compare_posts(native,{'schema':1,'rows':observations},1,421,
        fields=('action','stocks','animation','x','y','percent','facing'),compare_settings=False,player_indices=MATCH.ports)
    report={'schema':1,'passed':states['passed'] and phase['passed'],
        'native_vs_official_postframes':states,'native_observation_phase_check':phase,
        'source_replay_sha256':sha256(replay),'source_video_reconstruction_tested':False,
        'full_state_equality_measured':False,'render_phase_alignment_measured':False,
        'identities':{str(p):sha256(p) for p in (Path(__file__),root/'probe-result.json',root/'official/capture.json',
            out/'native-state.json',out/'official-state.json',Path('src/yt2slp/benchmark.py'))}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('record').add_argument('--output',type=Path,required=True)
    sub.add_parser('verify').add_argument('--run',type=Path,required=True)
    a=parser.parse_args();return {'record':record,'verify':verify}[a.command](a)

if __name__=='__main__':raise SystemExit(main())
