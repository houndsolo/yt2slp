"""Host workflow for annotated consecutive windows and one genuine joined replay.

Run under xvfb-run. Plan paths use Docker workspace names (.local/... for local
artifacts). Native operations run in Docker; official GUI captures run on host.
Only final verify may receive optional known-source state, after all selections.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def host_path(value, root=ROOT):
    text=str(value)
    if text.startswith('/work/'):text=text[6:]
    path=Path(text)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('plan paths must stay inside the Docker workspace')
    if path.parts[0]=='.local':return root/'.docker-state/local'/Path(*path.parts[1:])
    return root/path


def logical(value):
    text=str(value)
    return text[6:] if text.startswith('/work/') else text


def read(path):return json.loads(path.read_text())


def digest(path):
    with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()


def last_report(output):
    decoder=json.JSONDecoder()
    # Native dependencies may log before/after the runner's JSON. Only a full
    # object at column zero with a run field is accepted as the runner result.
    for position in reversed([i for i,c in enumerate(output) if c=='{' and (i==0 or output[i-1]=='\n')]):
        try:report,_=decoder.raw_decode(output[position:])
        except json.JSONDecodeError:continue
        if isinstance(report,dict) and isinstance(report.get('run'),str):return report
    raise ValueError('runner did not return an identifiable run report')


def validate_plan(plan):
    if (plan.get('schema')!=1 or plan.get('kind')!='manual-window-plan'
            or not isinstance(plan.get('windows'),list) or not 2<=len(plan['windows'])<=32):
        raise ValueError('expected a plan with 2..32 annotated windows')
    main=read(host_path(plan['video'])/'video.json')
    previous=None;recipe=None
    for window in plan['windows']:
        spec=read(host_path(window['spec']))
        video=read(host_path(window['video'])/'video.json')
        if video['source_sha256']!=main['source_sha256']:
            raise ValueError('all windows must reference the same ingested source')
        this_recipe={k:spec[k] for k in ('rng_seed','time_base','known_match')}
        if recipe is not None and this_recipe!=recipe:raise ValueError('window start recipes differ')
        recipe=this_recipe
        if previous is not None and spec['checkpoint_frame']!=previous:
            raise ValueError('windows must be consecutive; no gaps or reset starts')
        previous=spec['end_frame']
        for key in ('timeline','regions'):
            if not host_path(window[key]).is_file():raise ValueError('missing source annotations')
    first,last=plan['render_interval']
    start=read(host_path(plan['windows'][0]['spec']))['checkpoint_frame']
    if not start<=first<=last<previous:raise ValueError('joined render interval is outside the selected trajectory')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True,help='host plan JSON; contents use Docker workspace paths')
    parser.add_argument('--output',required=True,help='new Docker artifact directory, e.g. .local/windows-NEW')
    parser.add_argument('--iso',type=Path,required=True)
    parser.add_argument('--dolphin',type=Path,required=True)
    parser.add_argument('--calibration',required=True,help='Docker workspace calibration path')
    parser.add_argument('--initial-search',help='optional existing first-window coarse run in Docker workspace')
    parser.add_argument('--reference-state',help='optional final-only verification ground truth in Docker workspace')
    a=parser.parse_args();plan=read(a.plan);validate_plan(plan)
    out=host_path(a.output);out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir()
    (out/'plan.json').write_text(a.plan.read_text())
    environment={**os.environ,'YT2SLP_ISO':str(a.iso.resolve())}
    windows=[];prefix=None;active='initialization'
    def run(stage,command):
        nonlocal active
        active=stage
        (out/'logs'/f'{stage}.command.json').write_text(json.dumps(command)+'\n')
        result=subprocess.run(command,cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        (out/'logs'/f'{stage}.log').write_text(result.stdout)
        if result.returncode:raise RuntimeError(f'{stage} failed; see its preserved log')
        print(stage+' complete',flush=True)
        return result.stdout
    def docker(stage,script,*arguments):return run(stage,['bash','scripts/docker.sh','run','python',script,*map(str,arguments)])
    try:
        for index,window in enumerate(plan['windows'],1):
            tag=f'window-{index}';directory=f'{a.output}/{tag}';candidates=directory+'/candidates';ranking=candidates+'/ranking'
            if index==1 and a.initial_search:
                search=logical(a.initial_search)
                if read(host_path(search)/'search-spec.json')!=read(host_path(window['spec'])):
                    raise ValueError('reused first-window search has a different specification')
            else:
                command=['--video',window['video'],'--timeline',window['timeline'],'--spec',window['spec']]
                if prefix:command+=['--prefix',prefix]
                search=logical(last_report(docker(tag+'-search','scripts/reconstruct_manual.py',*command))['run'])
            docker(tag+'-export','scripts/export_candidates.py','--search',search,'--video',window['video'],'--output',candidates,'--max-candidates','32')
            run(tag+'-capture',['python','scripts/capture_candidates.py','--candidates',str(host_path(candidates)),
                '--dolphin',str(a.dolphin.resolve()),'--iso',str(a.iso.resolve())])
            command=['rank','--candidates',candidates,'--video',window['video'],'--regions',window['regions'],
                '--calibration',a.calibration,'--output',ranking]
            if window.get('manual_timers'):command+=['--manual-timers',window['manual_timers']]
            docker(tag+'-rank','scripts/rank_candidates.py',*command)
            command=['--video',window['video'],'--timeline',window['timeline'],'--spec',ranking+'/selected-spec.json']
            if prefix:command+=['--prefix',ranking+'/prefix.json']
            fresh=logical(last_report(docker(tag+'-fresh','scripts/reconstruct_manual.py',*command))['run'])
            chosen=read(host_path(ranking)/'ranking.json')
            origin=host_path(candidates)/f"candidate-{chosen['selected_index']:03d}"/'official'
            current=host_path(fresh)
            capture=read(origin/'capture.json')
            if digest(current/'selected.slp')!=capture['source_replay_sha256'] or not capture['capture_passed']:
                raise ValueError('fresh replay does not match its actual official capture')
            (current/'official').symlink_to(os.path.relpath(origin,current),target_is_directory=True)
            (current/'capture-reuse.json').write_text(json.dumps({'policy':'actual official capture of a byte-identical genuine replay',
                'origin':str(origin),'capture_sha256':digest(origin/'capture.json'),'replay_sha256':capture['source_replay_sha256']},indent=2)+'\n')
            command=['--run',fresh,'--video',window['video'],'--calibration',a.calibration]
            if window.get('manual_timers'):command+=['--manual-timers',window['manual_timers']]
            docker(tag+'-review','scripts/review_manual.py',*command)
            prefix=directory+'/prefix.json'
            docker(tag+'-seal','scripts/trajectory.py','seal','--ranking',ranking,'--run',fresh,'--output',prefix)
            windows.append({'search':search,'fresh':fresh,'ranking':ranking,'prefix':prefix,
                'selected_schedule':chosen['selected_schedule'],'equally_best_indices':chosen['equally_best_indices']})
            (out/'completed-windows.json').write_text(json.dumps(windows,indent=2)+'\n')
        joined=a.output+'/joined'
        docker('joined-fresh','scripts/trajectory.py','validate','--prefix',prefix,'--video',plan['video'],
            '--timeline',plan['timeline'],'--output',joined)
        first,last=plan['render_interval']
        run('joined-capture',['python','scripts/capture_benchmark.py','--dolphin',str(a.dolphin.resolve()),'--iso',str(a.iso.resolve()),
            '--replay',str(host_path(joined)/'selected.slp'),'--output',str(host_path(joined)/'official'),
            '--first',str(first),'--last',str(last),'--padding','0'])
        command=['--run',joined,'--video',plan['video'],'--calibration',a.calibration]
        if plan.get('manual_timers'):command+=['--manual-timers',plan['manual_timers']]
        docker('joined-review','scripts/review_manual.py',*command)
        command=['verify','--prefix',prefix,'--run',joined]
        if a.reference_state:command+=['--reference-state',a.reference_state]
        docker('joined-verify','scripts/trajectory.py',*command)
        report={'schema':1,'pipeline_checks_passed':True,'windows':windows,'joined':joined,
            'visual_accuracy_accepted':False,'original_inputs_identified':False,'backtracking_implemented':False,
            'plan_sha256':digest(a.plan),'runner_sha256':digest(Path(__file__))}
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    except Exception as exc:
        (out/'failure.json').write_text(json.dumps({'failed_stage':active,'error':str(exc),'completed_windows':windows},indent=2)+'\n')
        raise

if __name__=='__main__':main()
