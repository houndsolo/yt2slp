"""Bounded two-player opening search using signed replay-frame observations.

Supplied match settings and seed/time-base hypotheses remain explicit. Sparse
cue acceptance is not visual acceptance. No source replay/hidden-state input.
Run in Docker; a failed grid retains trials and exports no replay.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess

from yt2slp.backend import NativeLinuxBackend, RunConfig
from yt2slp.match import match_from_document
from yt2slp.search import bounded_search, run_recorded_schedule, schedule_from_dict, TwoPlayerSequence
from yt2slp.timeline import load_timeline
from yt2slp.video import sha256

BOOT=Path('third_party/melee-unlocked/port/scripts/native_vs.txt')


def advance_opening(backend,match):
    key=backend.recording_status().last_frame
    if key!=-123:raise ValueError('opening requires the measured -123 early pause')
    while key<-40:
        backend.step(match.neutral_pads());current=backend.recording_status().last_frame
        if current!=key+1:raise ValueError('neutral Ready prefix did not advance one recorded frame per VI')
        key=current


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('video','timeline','spec'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();spec=json.loads(a.spec.read_text());video=json.loads((a.video/'video.json').read_text())
    if (spec.get('schema')!=1 or spec.get('kind')!='manual-replay-frame-search'
            or spec.get('checkpoint_frame')!=-40 or not isinstance(spec.get('start_source'),str)
            or not spec['start_source'].strip()):raise ValueError('explicit pre-playable opening recipe required')
    end=spec['end_frame']
    if type(end) is not int or not 1<=end<=560:raise ValueError('opening ends at replay frame 1..560')
    for key,limit in [('rng_seed',0xFFFFFFFF),('time_base',0xFFFFFFFFFFFFFFFF)]:
        if type(spec[key]) is not int or not 0<=spec[key]<=limit:raise ValueError('explicit integer simulation seed/time base required')
    match=match_from_document(spec['match'])
    candidates=tuple(schedule_from_dict(c) for c in spec['candidates'])
    if any(not isinstance(c,TwoPlayerSequence) for c in candidates):raise ValueError('opening search requires two explicit player programs')
    samples=load_timeline(json.loads(a.timeline.read_text()),video)
    if any(s.frame_clock!='slippi-replay' for s in samples):raise ValueError('opening annotations require signed replay-frame keys')
    for s in samples:
        row=video['frames'][s.video_frame]
        if sha256(a.video/row['image'])!=row['image_sha256']:raise ValueError('annotated source image identity differs')
    config=RunConfig(Path('build/headless/melee_headless'),Path('build/game/melee_game.so'),
        Path(os.environ.get('YT2SLP_ISO','/assets/melee.iso')),Path('.local/runs'),spec['rng_seed'],spec['time_base'],match,
        spec.get('rng_seed_boundary','item-setup'))
    with NativeLinuxBackend() as backend:
        backend.initialize(config);backend.start(BOOT,timeout=180,include_preroll=True)
        root=backend.last_run_dir
        (root/'search-spec.json').write_text(a.spec.read_text());(root/'timeline.json').write_text(a.timeline.read_text())
        advance_opening(backend,match)
        report=bounded_search(backend,samples,candidates,end+40,root/'trials',frame_clock='slippi-replay',player_ports=match.ports)
        report.update(source_video_sha256=video['source_sha256'],requested_match=asdict(match),start_source=spec['start_source'],
            source_hidden_state_recovered=False,original_inputs_identified=False,visual_accuracy_accepted=False,
            simulation_seed=spec['rng_seed'],simulation_time_base=spec['time_base'],
            simulation_rng_seed_boundary=config.rng_seed_boundary,parser_validated=False,
            official_playback_validated=False,pixel_agreement_measured=False,
            identities={str(path):sha256(path) for path in (Path(__file__),a.spec,a.timeline,a.video/'video.json',
                config.host,config.game_library,config.iso,BOOT,Path('src/yt2slp/search.py'),Path('src/yt2slp/timeline.py'),Path('src/yt2slp/match.py'))})
        if report['passed']:
            status=backend.recording_status()
            if status.last_frame!=end or status.ended:raise ValueError('unexpected recording boundary')
            backend.record(root/'selected.slp');selected=backend.observations
            (root/'selected-observations.json').write_text(json.dumps([asdict(s) for s in selected])+'\n')
            chosen=json.loads((root/f"trials/{report['selected_index']:03d}.json").read_text())
            with NativeLinuxBackend() as fresh:
                fresh.initialize(config);fresh.start(BOOT,timeout=180,include_preroll=True);advance_opening(fresh,match)
                _,keys=run_recorded_schedule(fresh,schedule_from_dict(report['selected_schedule']),end+40)
                fresh.record(root/'fresh-selected.slp')
                report['fresh_selected_observations_match']=fresh.observations==selected
                report['fresh_recording_keys_match']=list(keys)==chosen['replay_frame_keys']
                report['fresh_recording_bytes_match']=sha256(root/'selected.slp')==sha256(root/'fresh-selected.slp')
            with (root/'parser-result.json').open('x') as handle:
                subprocess.run(['node','tools/slippi-parser/validate.cjs',str(root/'selected.slp'),'--last-frame',str(end)],check=True,stdout=handle)
            parsed=json.loads((root/'parser-result.json').read_text());settings=parsed['settings']
            actual=[(p['playerIndex'],p['characterId'],p['characterColor']) for p in settings['players']]
            expected=sorted((port,p.character,p.costume) for port,p in zip(match.ports,match.players))
            if (settings['stageId']!=match.stage or actual!=expected or settings['isTeams']
                    or parsed['replaySha256']!=sha256(root/'selected.slp') or parsed['gameEnd'] is not None):
                raise ValueError('independent parser settings/identity differ from requested partial recording')
            if match.stock_rules and (settings['startingTimerSeconds']!=match.stock_rules.seconds
                    or settings['inGameMode']!=32 or any(p['startStocks']!=match.stock_rules.stocks for p in settings['players'])):
                raise ValueError('parsed stock rules differ')
            if config.rng_seed_boundary=='slippi-game-start' and settings['randomSeed']!=config.rng_seed:
                raise ValueError('recorded Game Start seed differs from explicit initial seed')
            report['parser_validated']=True;report['selected_replay_sha256']=sha256(root/'selected.slp')
            report['passed'] &= all(report[k] for k in ('fresh_selected_observations_match','fresh_recording_keys_match','fresh_recording_bytes_match'))
        (root/'search-result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'run':str(root),**{k:report[k] for k in ('passed','candidate_count','accepted_indices','selected_index')}},indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
