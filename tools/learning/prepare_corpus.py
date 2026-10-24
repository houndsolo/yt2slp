"""Detached server-local corpus capture, audit and GPU feature preparation.

Test sources are never opened. Failed clips stay excluded, with their evidence;
the frozen selection is never changed to chase good validation performance.
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

from train_smoke import torch, encode_images
from baseline import targets_for_frames
from manage import validate_config
from runtime_files import ROOT, atomic_json, digest, read_json, status
from yt2slp.corpus import corpus_ports, select_corpus_clips
from yt2slp.learning_data import validate_split_plan
from yt2slp.model_contract import image_view


def run(command,log):
    with log.open('a') as handle:
        handle.write('\nCOMMAND '+repr(list(map(str,command)))+'\n'); handle.flush()
        subprocess.run(list(map(str,command)),cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT,check=True)


def render_clip(clip,folder,config):
    for attempt in range(3):
        try: return render_once(clip,folder,config)
        except subprocess.CalledProcessError as error:
            # Retry capture transport/startup only, retaining each attempt.
            # Audit, state, label and identity failures are not retried here.
            if not error.cmd or error.cmd[0]!='xvfb-run' or attempt==2: raise
            print(json.dumps({'stage':'capture-retry','clip':clip['clip_id'],'attempt':attempt+2}),flush=True)


def render_once(clip,folder,config):
    folder.mkdir(parents=True,exist_ok=True)
    ready=read_json(folder/'prepared.json')
    if ready:
        if any(digest(ROOT/p)!=expected for p,expected in ready['identities'].items()):
            raise ValueError('prepared video identity changed; preserve evidence')
        return ready
    replay=ROOT/clip['file']
    if digest(replay)!=clip['replay_sha256']: raise ValueError('source replay changed')
    if shutil.disk_usage(ROOT).free<config['minimum_free_gib']*2**30: raise RuntimeError('storage reserve reached; free space and resume preparation')
    first,last=clip['interval']; attempt=folder/f'attempt-{time.time_ns()}'; attempt.mkdir()
    capture=attempt/'capture'; video=attempt/'video'; labels=attempt/'labels.json'; log=attempt/'preparation.log'
    reusable=[]
    for receipt in sorted(folder.glob('attempt-*/capture/capture.json')):
        old=read_json(receipt)
        if old.get('capture_passed') is True and old.get('source_replay_sha256')==clip['replay_sha256'] and old.get('wanted_interval')==clip['interval']:
            rows=read_json(receipt.parent/'capture-index.json')
            if all(digest(receipt.parent/'user/Dump/Frames'/r['capture_image'])==r['capture_image_sha256'] for r in rows): reusable.append(receipt.parent)
    print(json.dumps({'stage':'capture/audit','clip':clip['clip_id'],'split':clip['split'],'interval':clip['interval']}),flush=True)
    if reusable:
        capture=reusable[-1]
        atomic_json(attempt/'capture-reference.json',{'capture':str(capture.relative_to(ROOT)),'sha256':digest(capture/'capture.json')})
    else:
        run(['xvfb-run','-a','-s','-screen 0 1024x768x24',sys.executable,'scripts/capture_signed_frames.py',
            '--dolphin',ROOT/config['playback'],'--iso',ROOT/config['iso'],'--replay',replay,
            '--osd-calibration',ROOT/config['osd_calibration'],'--first',first,'--last',last,
            '--per-step-log-association','--timeout',1200,'--output',capture],log)
    run([sys.executable,'scripts/prepare_signed_video.py','--replay',replay,'--capture',capture,
        '--timer-calibration',ROOT/config['timer_calibration'],'--pipeline-phase-reference',ROOT/config['phase_reference'],
        '--hud-policy','corpus-v1','--output',video],log)
    with labels.open('x') as handle:
        subprocess.run(['node','tools/slippi-parser/export-training.cjs',str(replay),str(first),str(last)],cwd=ROOT,stdout=handle,check=True)
    targets=read_json(labels)
    # Physical labels must be present, rather than becoming all-zero supervision.
    if any(not r['physical']['mask']['buttons'] or not r['physical_edges']['mask'] for r in targets['rows']):
        raise ValueError('missing original physical-button or edge labels')
    bound=(video/'source.mp4',video/'source-provenance.json',video/'capture-index.json',video/'frame-labels.json',
           video/'phase-audit.json',video/'ingested/video.json',labels)
    result={'video':str(video.relative_to(ROOT)),'labels':str(labels.relative_to(ROOT)),
        'identities':{str(p.relative_to(ROOT)):digest(p) for p in bound}}
    atomic_json(folder/'prepared.json',result)
    return result


def cache_clip(clip,ready,folder,context,device):
    view_path=folder/'images.json'; video=ROOT/ready['video']; labels_path=ROOT/ready['labels']
    view=read_json(view_path) if view_path.exists() else image_view(video,view_path)
    provenance=read_json(video/'source-provenance.json'); phase=read_json(video/'phase-audit.json')
    audit=read_json(video/'frame-labels.json'); labels=read_json(labels_path)
    if (provenance.get('passed') is not True or audit.get('passed') is not True
            or phase.get('kind')!='image-post-phase-pipeline-reference' or phase.get('passed') is not True
            or phase['image_to_post_offset']!=0 or phase['source_replay_sha256']!=clip['replay_sha256']
            or not {digest(video/'phase-audit.json'),digest(video/'frame-labels.json')} <= set(provenance['identities'].values())
            or provenance['interval']!=clip['interval'] or view['replay_sha256']!=clip['replay_sha256']
            or labels['replay_sha256']!=clip['replay_sha256'] or labels['interval']!=clip['interval']):
        raise ValueError('identity-bound corpus phase, frame and label evidence required')
    ports=corpus_ports(view['settings'])
    signature=lambda s:sorted((p['port'],p['character'],p['costume']) for p in s['players'])
    if (corpus_ports(labels['settings'])!=ports or signature(clip)!=signature(labels['settings'])
            or signature(view['settings'])!=signature(labels['settings'])):
        raise ValueError('label roster/costume/physical slots differ from images or selection')
    keyed={(r['frame'],r['port']):r for r in labels['rows']}
    if len(keyed)!=len(labels['rows']): raise ValueError('duplicate label key')
    rows=[{'targets':[keyed[f['replay_frame'],p] for p in ports]} for f in view['frames']]
    features=encode_images(view_path,view,32,device)
    payload=folder/'features.pt'; temporary=folder/'features.tmp'
    torch.save({'features':features,'targets':targets_for_frames(rows),'replay_sha256':clip['replay_sha256']},temporary)
    temporary.replace(payload)
    info={k:clip[k] for k in ('clip_id','replay_sha256','split','group','interval','file')}
    info.update(frames=len(rows),windows=len(rows)-context+1,first_frame=clip['interval'][0],context_frames=context,
        slot_ports=ports,slot_characters=[p['character'] for p in sorted(view['settings']['players'],key=lambda p:p['port'])],
        feature_size=features.shape[1],payload_sha256=digest(payload),labels_sha256=digest(labels_path),
        image_view_sha256=digest(view_path),video=ready['video'],labels=ready['labels'],
        preprocessing_sha256=digest(Path(__file__).with_name('train_smoke.py')),
        encoder_weights_sha256=digest(Path(torch.hub.get_dir())/'checkpoints/resnet18-f37072fd.pth'),
        hud_corroboration=audit['hud_corroboration'],phase_independently_reviewed=False)
    atomic_json(folder/'shard.json',info)
    return info


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--limit',type=int,help='prepare a bounded validation subset; publish preview only')
    args=parser.parse_args(); config=read_json(args.config); validate_config(config)
    if args.limit is not None and args.limit<1: raise ValueError('positive preview count required')
    output=ROOT/config['data_directory']; output.mkdir(parents=True,exist_ok=True); progress=output/'preparation-status.json'
    try:
        if not torch.cuda.is_available(): raise ValueError('CUDA unavailable; no fallback')
        torch.set_num_threads(config['threads']); torch.cuda.set_per_process_memory_fraction(config['gpu_memory_fraction'])
        plan_path=ROOT/config['split_plan']; plan=read_json(plan_path)
        selection={'schema':1,'kind':'frozen-corpus-clip-selection','plan_sha256':digest(plan_path),'clips':select_corpus_clips(plan)}
        frozen=read_json(output/'selection.json')
        if frozen and frozen!=selection: raise ValueError('frozen corpus selection differs; use a new data directory')
        atomic_json(output/'selection.json',selection)
        sources=['tools/learning/prepare_corpus.py','tools/learning/train_smoke.py','scripts/capture_signed_frames.py',
            'scripts/prepare_signed_video.py','src/yt2slp/corpus.py','src/yt2slp/frame_index.py',
            'src/yt2slp/training_phase.py','src/yt2slp/timer_labels.py','tools/slippi-parser/export-training.cjs',
            'tools/slippi-parser/package-lock.json']
        identity={'sources':{p:digest(ROOT/p) for p in sources},'config_sha256':digest(args.config),
            'inputs':{k:digest(ROOT/config[k]) for k in ('iso','playback','osd_calibration','timer_calibration','phase_reference')},
            'encoder_weights_sha256':digest(Path(torch.hub.get_dir())/'checkpoints/resnet18-f37072fd.pth'),
            'torch_version':str(torch.__version__),
            'plan_sha256':digest(plan_path),'hud_policy':'corpus-v1'}
        old=read_json(output/'preparation-contract.json')
        if old and old!=identity: raise ValueError('preparation code/config changed; preserve dataset and use a new directory')
        atomic_json(output/'preparation-contract.json',identity)
        clips=selection['clips'][:args.limit] if args.limit else selection['clips']
        shards=[]; failures=[]; started=time.monotonic()
        def report(state,**more):
            return status(progress,state,total=len(clips),planned_total=len(selection['clips']),finished=len(shards)+len(failures),
                accepted=len(shards),failed_count=len(failures),elapsed_seconds=time.monotonic()-started,**more)
        report('preparing')
        with ThreadPoolExecutor(max_workers=config['preparation_workers']) as pool:
            pending={}
            for clip in clips:
                folder=output/'clips'/clip['clip_id']; info=read_json(folder/'shard.json')
                if info:
                    if digest(folder/'features.pt')!=info['payload_sha256']: raise ValueError('completed feature shard changed')
                    shards.append({**info,'payload':str((folder/'features.pt').relative_to(output))}); continue
                pending[pool.submit(render_clip,clip,folder,config)]=(clip,folder)
            for future in as_completed(pending):
                clip,folder=pending[future]
                try:
                    info=cache_clip(clip,future.result(),folder,config['context_frames'],torch.device('cuda'))
                    shards.append({**info,'payload':str((folder/'features.pt').relative_to(output))})
                    print(json.dumps({'stage':'ready','clip':clip['clip_id'],'accepted':len(shards)}),flush=True)
                except Exception as error:
                    failure={'clip':clip['clip_id'],'split':clip['split'],'error':str(error)}; failures.append(failure)
                    folder.mkdir(parents=True,exist_ok=True); atomic_json(folder/'last-failure.json',failure)
                    print(json.dumps({'stage':'failed',**failure}),flush=True)
                report('preparing',last_clip=clip['clip_id'])
        shards.sort(key=lambda s:s['clip_id'])
        if any(s['encoder_weights_sha256']!=identity['encoder_weights_sha256'] for s in shards):
            raise ValueError('encoder weights differ across corpus shards')
        manifest={'schema':1,'kind':'vision-corpus-feature-dataset','stage':31,'slot_mapping':'ascending-physical-ports',
            'context_frames':config['context_frames'],'split_plan':os.path.relpath(plan_path,output),
            'split_plan_sha256':digest(plan_path),'selection':'selection.json','selection_sha256':digest(output/'selection.json'),
            'shards':shards,'failures':failures,'test_matches_opened':0,'hud_policy':'corpus-v1',
            'phase_policy':'experimental same-pipeline zero-phase transfer; independent target-roster phase review not established',
            'generalization_established':False,'native_vi_adapter_verified':False}
        if args.limit:
            atomic_json(output/'preview-dataset.json',manifest); report('preview-complete',failures=failures); return 0 if shards else 1
        counts={s:len({c['replay_sha256'] for c in shards if c['split']==s}) for s in ('train','validation')}
        if counts['train']<config['minimum_train_matches'] or counts['validation']<config['minimum_validation_matches']:
            raise ValueError('too few audited matches; retain failures and retry preparation')
        for split in counts:
            for roster in ([2,2],[2,20]):
                if not any(s['split']==split and sorted(s['slot_characters'])==roster for s in shards):
                    raise ValueError('both rosters required in each development split')
        atomic_json(output/'dataset.json',manifest)
        report('ready',match_counts=counts,frames=sum(s['frames'] for s in shards),
            windows={s:sum(c['windows'] for c in shards if c['split']==s) for s in counts},failures=failures)
    except BaseException as error:
        status(progress,'failed',error=str(error)); raise


if __name__=='__main__': main()
