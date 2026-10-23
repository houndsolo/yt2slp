"""Genuine checkpoint/recording checks before the match clock begins.

The stock Yoshi/Falco/Captain configuration is a declared control probe. It is
not a reconstruction of the tournament video's input sequence.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess

from yt2slp.backend import NativeLinuxBackend, RunConfig
from yt2slp.benchmark import compare_posts, observation_rows
from yt2slp.match import PadInput
from yt2slp.video import sha256
from probe_tournament_start import MATCH, BOOT, read, export


def sample(backend):
    return {'replay_frame':backend.recording_status().last_frame,'observation':asdict(backend.observe())}


def step(backend,pads):
    before=backend.recording_status().last_frame
    backend.step(pads);result=sample(backend)
    if result['replay_frame']!=before+1:raise ValueError('probe requires one recorded frame per VI')
    return result


def warmup(backend):
    result=[sample(backend)]
    if result[0]['replay_frame']!=-123 or result[0]['observation']['match_frame']!=0:
        raise ValueError('early pause is not at the declared recorded opening')
    while result[-1]['replay_frame']<-40:result.append(step(backend,MATCH.neutral_pads()))
    return result


def continuation(backend,neutral=False):
    result=[]
    for index in range(180):
        pads=list(MATCH.neutral_pads())
        if not neutral:
            pads[1]=PadInput(button=0x400 if 6<=index<8 else 0)
            pads[2]=PadInput(stick_x=-80 if index<20 else 0)
        result.append(step(backend,tuple(pads)))
    return result


def record(a):
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    config=RunConfig(Path('build/headless/melee_headless'),Path('build/game/melee_game.so'),
        Path(os.environ.get('YT2SLP_ISO','/assets/melee.iso')),Path('.local/runs'),match=MATCH)
    report={'schema':1,'kind':'preroll-control-probe','passed':False,'requested_match':asdict(MATCH),
        'source_inputs_recovered':False,'reconstruction_attempted':False,'full_state_equality_measured':False}
    try:
        with NativeLinuxBackend() as backend:
            backend.initialize(config);backend.start(BOOT,timeout=180,include_preroll=True)
            prefix=warmup(backend);captured=sample(backend);handle=backend.capture()
            first=continuation(backend);backend.record(out/'original.slp')
            backend.restore(handle);report['restored_pause_stable']=sample(backend)==captured
            repeated=continuation(backend);backend.record(out/'repeated.slp')
            backend.restore(handle);neutral=continuation(backend,True);backend.record(out/'neutral.slp')
            backend.restore(handle);selected=continuation(backend);backend.record(out/'selected.slp')
            trace=prefix+selected
            (out/'observations.json').write_text(json.dumps(trace)+'\n')
            report.update(native_run=str(backend.last_run_dir),initial_replay_frame=prefix[0]['replay_frame'],
                checkpoint_replay_frame=captured['replay_frame'],checkpoint_match_counter=captured['observation']['match_frame'],
                last_replay_frame=backend.recording_status().last_frame,ended=backend.recording_status().ended,
                same_continuations=first==repeated==selected,
                both_players_diverge_before_frame_zero={str(port):any(x['replay_frame']<0 and
                    x['observation']['fighters'][port]!=y['observation']['fighters'][port]
                    for x,y in zip(first,neutral)) for port in MATCH.ports})
        with NativeLinuxBackend() as fresh:
            fresh.initialize(config);fresh.start(BOOT,timeout=180,include_preroll=True)
            fresh_trace=warmup(fresh)+continuation(fresh);fresh.record(out/'fresh.slp')
            report['fresh_observations_match']=fresh_trace==trace
        hashes={name:sha256(out/f'{name}.slp') for name in ('original','repeated','neutral','selected','fresh')}
        report['replay_hashes']=hashes
        report['selected_bytes_reproduce']=len({hashes[k] for k in ('original','repeated','selected','fresh')})==1
        report['discarded_branch_differs']=hashes['neutral']!=hashes['selected']
        with (out/'parser-result.json').open('x') as handle:
            subprocess.run(['node','tools/slippi-parser/validate.cjs',str(out/'selected.slp'),'--last-frame','140'],check=True,stdout=handle)
        parsed=read(out/'parser-result.json')
        report['parser_validated']=parsed['replaySha256']==hashes['selected'] and parsed['gameEnd'] is None
        report['identities']={str(p):sha256(p) for p in (Path(__file__),Path('scripts/probe_tournament_start.py'),
            config.host,config.game_library,config.iso,BOOT,out/'observations.json',out/'parser-result.json')}
        report['passed']=(report['last_replay_frame']==140 and not report['ended'] and report['restored_pause_stable']
            and report['same_continuations'] and all(report['both_players_diverge_before_frame_zero'].values())
            and report['fresh_observations_match'] and report['selected_bytes_reproduce']
            and report['discarded_branch_differs'] and report['parser_validated'])
        if not report['passed']:raise ValueError('preroll control/recording probe failed')
    except Exception as exc:
        report['error']=str(exc);(out/'probe-result.json').write_text(json.dumps(report,indent=2)+'\n');raise
    (out/'probe-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


def verify(a):
    root=a.run.resolve();prior=read(root/'probe-result.json');capture=read(root/'official/capture.json')
    if (not prior['passed'] or not capture['capture_passed'] or capture['should_resync'] is not False
            or capture['wanted_interval']!=[-39,140] or not capture['include_preroll']
            or sha256(root/'selected.slp')!=prior['replay_hashes']['selected']
            or capture['source_replay_sha256']!=prior['replay_hashes']['selected']
            or len(capture['regenerated_replays'])!=1
            or prior['identities']['/assets/melee.iso'] not in capture['identities'].values()):
        raise ValueError('preroll probe lacks bound native/parser/official evidence')
    out=a.output.resolve() if a.output else root/'official-analysis';out.mkdir(exist_ok=False)
    native=export(root/'selected.slp',out/'native-state.json')
    official=export(root/'official'/capture['regenerated_replays'][0],out/'official-state.json')
    states=compare_posts(native,official,-123,140,player_indices=MATCH.ports)
    requested=compare_posts(native,official,*capture['wanted_interval'],player_indices=MATCH.ports)
    # Preserve the raw zero counter separately. The signed label is observed
    # from recording_status at the same paused boundary, not fitted to pixels.
    observed=[]
    for entry in read(root/'observations.json'):
        for row in observation_rows([entry['observation']],MATCH.ports):
            row['frame']=entry['replay_frame'];observed.append(row)
    phase=compare_posts(native,{'schema':1,'rows':observed},-123,140,
        fields=('action','stocks','animation','x','y','percent','facing'),compare_settings=False,player_indices=MATCH.ports)
    report={'schema':1,'passed':states['passed'] and phase['passed'],
        'native_vs_official_postframes':states,'native_observation_phase_check':phase,
        'requested_playable_interval_comparison':requested,
        'requested_playable_interval_checks_passed':requested['passed'] and phase['passed'],
        'policy':'full recording gate remains strict; requested capture interval is reported separately, without tolerance or frame fitting',
        'source_replay_sha256':sha256(root/'selected.slp'),'source_video_reconstruction_tested':False,
        'full_state_equality_measured':False,'render_phase_alignment_measured':False,
        'identities':{str(p):sha256(p) for p in (Path(__file__),root/'probe-result.json',root/'official/capture.json',
            out/'native-state.json',out/'official-state.json',root/'observations.json',Path('src/yt2slp/benchmark.py'))}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('record').add_argument('--output',type=Path,required=True)
    verification=sub.add_parser('verify')
    verification.add_argument('--run',type=Path,required=True)
    verification.add_argument('--output',type=Path,help='new analysis directory; retain earlier failed audits')
    a=parser.parse_args();return {'record':record,'verify':verify}[a.command](a)

if __name__=='__main__':raise SystemExit(main())
