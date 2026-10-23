"""Seal image-selected windows, reproduce joined history, and verify after selection.

Run in Docker. A prefix is a selected controller history, not a portable game
checkpoint. No source replay/state is an input to seal or validate.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

from yt2slp.backend import NativeLinuxBackend, RunConfig
from yt2slp.benchmark import compare_posts
from yt2slp.match import MatchConfig
from yt2slp.timeline import load_timeline, score_timeline
from yt2slp.trajectory import native_identities, observation_document, reproduce_prefix, validate_prefix, validate_segments
from yt2slp.video import sha256


def read(path):return json.loads(path.read_text())


def seal(a):
    ranking,run=a.ranking.resolve(),a.run.resolve()
    rank,search,review=read(ranking/'ranking.json'),read(run/'search-result.json'),read(run/'review/review-result.json')
    if (not rank['refinement_checks_passed'] or not search['passed'] or not search['parser_validated']
            or not search['fresh_selected_observations_match'] or not search['fresh_recording_bytes_match']
            or not review['pipeline_checks_passed'] or not review['native_vs_official_selected_fields']['passed']
            or sha256(run/'selected.slp')!=rank['selected_replay_sha256']
            or search['selected_replay_sha256']!=rank['selected_replay_sha256']
            or search['selected_schedule']!=rank['selected_schedule']
            or search['source_video_sha256']!=rank['source_video_sha256']
            or sha256(run/'selected-observations.json')!=search['selected_observations_sha256']):
        raise ValueError('window lacks identity-bound selected/fresh/parser/official validation')
    spec=read(run/'search-spec.json')
    segments=search['trajectory_segments']
    validate_segments(segments)
    if segments[-1]!={'first':spec['checkpoint_frame'],'last':spec['end_frame'],'schedule':rank['selected_schedule']}:
        raise ValueError('selected window differs from its joined controller history')
    previous=read(run/'prefix.json') if (run/'prefix.json').exists() else None
    if previous and (segments[:-1]!=previous['segments'] or search['prefix_reproduction_passed'] is not True):
        raise ValueError('selected window did not reproduce its sealed prefix')
    selections=previous['selections'].copy() if previous else []
    selections.append({'window':search['window'],'equally_best_indices':rank['equally_best_indices'],
        'selected_index':rank['selected_index'],'ranking_sha256':sha256(ranking/'ranking.json'),
        'search_sha256':sha256(run/'search-result.json'),'review_sha256':sha256(run/'review/review-result.json')})
    prefix={'schema':1,'kind':'selected-trajectory-prefix','segments':segments,'selections':selections,
        'source_video_sha256':search['source_video_sha256'],'native_identities':search['native_identities'],
        'start_recipe':{k:spec[k] for k in ('rng_seed','time_base','known_match')},
        'last_observation':read(run/'selected-observations.json')[-1],
        'replay_sha256':rank['selected_replay_sha256'],'policy':'carry one rendered minimum; retain tie evidence; no automatic backtracking',
        'source_player_state_used_for_selection':False,'backtracking_implemented':False,'global_search_exhausted':False}
    if prefix['last_observation']['match_frame']!=segments[-1]['last']:
        raise ValueError('selected boundary observation has wrong frame')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as handle:handle.write(json.dumps(prefix,indent=2)+'\n')
    print(a.output)


def validate(a):
    prefix,video=read(a.prefix),read(a.video/'video.json')
    timeline=read(a.timeline)
    samples=load_timeline(timeline,video)
    recipe=prefix['start_recipe']
    config=RunConfig(Path('build/headless/melee_headless'),Path('build/game/melee_game.so'),
        Path(os.environ.get('YT2SLP_ISO','/assets/melee.iso')),Path('.local/runs'),
        rng_seed=recipe['rng_seed'],time_base=recipe['time_base'],match=MatchConfig())
    boot=Path('third_party/melee-unlocked/port/scripts/native_vs.txt')
    end=prefix['segments'][-1]['last']
    validate_prefix(prefix,{**recipe,'checkpoint_frame':end},video['source_sha256'],native_identities(config,boot))
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'prefix.json').write_text(a.prefix.read_text())
    (out/'timeline.json').write_text(a.timeline.read_text())
    try:
        with NativeLinuxBackend() as original:
            original.initialize(config);original.start(boot,timeout=180)
            reproduce_prefix(original,prefix,out/'selected.slp')
            trace=original.observations
            score=score_timeline(samples,trace)
            if not score['accepted']:raise ValueError('joined history no longer fits all supplied visual cues')
            (out/'selected-observations.json').write_text(json.dumps([observation_document(o) for o in trace])+'\n')
            with NativeLinuxBackend() as fresh:
                fresh.initialize(config);fresh.start(boot,timeout=180)
                reproduce_prefix(fresh,prefix,out/'fresh-selected.slp')
                if trace!=fresh.observations:raise ValueError('joined trajectory observations differ on a fresh boot')
        with (out/'parser-result.json').open('x') as handle:
            subprocess.run(['node','tools/slippi-parser/validate.cjs',str(out/'selected.slp'),'--last-frame',str(end)],stdout=handle,check=True)
        report={'schema':1,'kind':'joined-window-validation','passed':True,'parser_validated':True,
            'fresh_selected_observations_match':True,'fresh_recording_bytes_match':True,
            'selected_replay_sha256':sha256(out/'selected.slp'),'source_video_sha256':video['source_sha256'],
            'selected_schedule':{'segments':prefix['segments']},'selected_score':score,
            'window':[prefix['segments'][0]['first'],end],'prefix_sha256':sha256(a.prefix),
            'backtracking_implemented':False,'visual_accuracy_accepted':False,'original_inputs_identified':False,
            'identities':{str(p):sha256(p) for p in (Path(__file__),a.prefix,a.timeline,a.video/'video.json',
                config.host,config.game_library,config.iso,boot,Path('src/yt2slp/trajectory.py'),out/'selected-observations.json')}}
        (out/'search-result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'run':str(out),'passed':True,'windows':len(prefix['segments']),'replay_sha256':report['selected_replay_sha256']},indent=2))
    except Exception as exc:
        (out/'trajectory-failure.json').write_text(json.dumps({'error':str(exc)},indent=2)+'\n')
        raise


def verify(a):
    prefix,search,review=read(a.prefix),read(a.run/'search-result.json'),read(a.run/'review/review-result.json')
    if (search['kind']!='joined-window-validation' or not search['passed'] or not search['parser_validated']
            or not search['fresh_recording_bytes_match'] or not search['fresh_selected_observations_match']
            or not review['pipeline_checks_passed'] or not review['native_vs_official_selected_fields']['passed']
            or search['prefix_sha256']!=sha256(a.prefix) or sha256(a.run/'prefix.json')!=sha256(a.prefix)
            or search['selected_replay_sha256']!=prefix['replay_sha256']
            or sha256(a.run/'selected.slp')!=prefix['replay_sha256']):
        raise ValueError('joined trajectory lacks its bound prefix/fresh/parser/official checks')
    oracle=None
    if a.reference_state:
        interval=review['native_vs_official_selected_fields']['interval']
        oracle=compare_posts(read(a.reference_state),read(a.run/'review/selected-state.json'),*interval)
    report={'schema':1,'passed':oracle is None or oracle['passed'],'window_count':len(prefix['segments']),
        'replay_sha256':prefix['replay_sha256'],'post_selection_reference_fields':oracle,
        'whole_clip_rgb_rmse':review['source_vs_reconstruction_pixel_diagnostic']['rgb_rmse_0_to_255'],
        'visual_accuracy_accepted':False,'original_inputs_identified':False,'full_state_equality_measured':False,
        'backtracking_implemented':False,'identities':{str(p):sha256(p) for p in (a.prefix,a.run/'search-result.json',a.run/'review/review-result.json')}}
    if a.reference_state:report['identities'][str(a.reference_state)]=sha256(a.reference_state)
    with (a.run/'trajectory-verification.json').open('x') as handle:handle.write(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('passed','window_count','whole_clip_rgb_rmse')},indent=2))
    return 0 if report['passed'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    seal_args=sub.add_parser('seal')
    for name in ('ranking','run','output'):seal_args.add_argument('--'+name,type=Path,required=True)
    validation=sub.add_parser('validate')
    for name in ('prefix','video','timeline','output'):validation.add_argument('--'+name,type=Path,required=True)
    verification=sub.add_parser('verify')
    for name in ('prefix','run'):verification.add_argument('--'+name,type=Path,required=True)
    verification.add_argument('--reference-state',type=Path,help='optional ground truth, only after every window is selected')
    a=parser.parse_args()
    return {'seal':seal,'validate':validate,'verify':verify}[a.command](a)

if __name__=='__main__':raise SystemExit(main())
