"""Server-local official capture -> audited images -> bounded feature shards.

Test matches are never selected or opened. Successful shards survive restarts;
failed attempts are retained and retried in new directories. All game assets,
videos, labels and caches remain ignored.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from runtime_files import ROOT, atomic_json, digest, read_json, status
from train_smoke import encode_images
import torch
from baseline import targets_for_frames
from yt2slp.learning_data import validate_split_plan
from yt2slp.model_contract import image_view, slot_ports
from manage import validate_config


def select_matches(plan, train_count, validation_count):
    validate_split_plan(plan)
    selected = []
    for split, count in (('train',train_count),('validation',validation_count)):
        candidates = sorted((m for m in plan['matches'] if m['split']==split),
            key=lambda m:(not m.get('previously_examined',False),m['replay_sha256']))
        groups = set(); chosen = []
        for match in candidates:
            if match['group'] not in groups:
                chosen.append(match); groups.add(match['group'])
            if len(chosen)==count: break
        if len(chosen)!=count: raise ValueError(f'insufficient distinct {split} date groups')
        selected.extend(chosen)
    return selected


def run(command, log):
    with log.open('a') as handle:
        handle.write('\nCOMMAND '+repr(list(map(str,command)))+'\n'); handle.flush()
        with subprocess.Popen(list(map(str,command)),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              text=True,bufsize=1,cwd=ROOT) as process:
            for line in process.stdout:
                handle.write(line); handle.flush(); print(line,end='',flush=True)
            code = process.wait()
        if code: raise subprocess.CalledProcessError(code,command)


def cache_clip(video, labels_path, output, context, device):
    view_path = output/f'images-{digest(video/"source-provenance.json")[:16]}.json'
    view = read_json(view_path) if view_path.exists() else image_view(video,view_path)
    phase = read_json(video/'phase-audit.json'); frames = read_json(video/'frame-labels.json')
    provenance = read_json(video/'source-provenance.json'); labels = read_json(labels_path)
    if (phase['kind'] not in ('image-post-phase-audit','image-post-phase-reference') or not phase['passed']
            or phase['image_to_post_offset']!=0 or not frames['passed']
            or not {digest(video/'phase-audit.json'),digest(video/'frame-labels.json')} <= set(provenance['identities'].values())
            or labels['replay_sha256']!=view['replay_sha256']):
        raise ValueError('identity-bound signed frame/phase evidence and same-replay labels required')
    ports = slot_ports({'stage':31,'slot_characters':[2,20]},view['settings'])
    if slot_ports({'stage':31,'slot_characters':[2,20]},labels['settings'])!=ports:
        raise ValueError('controller label roster/ports differ from image setup')
    keyed = {(r['frame'],r['port']):r for r in labels['rows']}
    if len(keyed)!=len(labels['rows']): raise ValueError('duplicate target key')
    rows = [{'targets':[keyed[f['replay_frame'],p] for p in ports]} for f in view['frames']]
    features = encode_images(view_path,view,16,device)
    payload = output/'features.pt'
    torch.save({'features':features,'targets':targets_for_frames(rows),'replay_sha256':view['replay_sha256']},payload)
    info = {'replay_sha256':view['replay_sha256'],'frames':len(rows),'windows':len(rows)-context+1,
        'first_frame':view['frames'][0]['replay_frame'],'context_frames':context,'slot_ports':ports,
        'slot_characters':[2,20],'feature_size':features.shape[1],
        'payload_sha256':digest(payload),'labels_sha256':digest(labels_path),'image_view_sha256':digest(view_path),
        'phase_method':phase['kind'],'phase_independently_reviewed':phase['kind']=='image-post-phase-audit',
        'preprocessing_sha256':digest(Path(__file__).with_name('train_smoke.py')),
        'encoder_weights_sha256':digest(Path(torch.hub.get_dir())/'checkpoints/resnet18-f37072fd.pth')}
    atomic_json(output/'shard.json',info)
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/vision-v100.json')
    args = parser.parse_args(); config = read_json(args.config); validate_config(config)
    output = ROOT/config['data_directory']; output.mkdir(parents=True,exist_ok=True)
    progress = output/'preparation-status.json'
    try:
        plan_path = ROOT/config['split_plan']; plan = read_json(plan_path)
        selection = {'schema':1,'plan_sha256':digest(plan_path),'last_frame':config['prepare_last_frame'],
            'context_frames':config['context_frames'],
            'matches':select_matches(plan,config['train_matches'],config['validation_matches'])}
        frozen = read_json(output/'selection.json')
        if frozen and frozen!=selection: raise ValueError('frozen selection differs; use a new data directory')
        atomic_json(output/'selection.json',selection)
        device = torch.device('cuda')
        if not torch.cuda.is_available(): raise ValueError('CUDA required for feature preparation; no fallback')
        torch.set_num_threads(config['threads']); torch.cuda.set_per_process_memory_fraction(config['gpu_memory_fraction'])
        shards = []; failures = []
        for number, match in enumerate(selection['matches'],1):
            directory = output/'clips'/match['replay_sha256']; directory.mkdir(parents=True,exist_ok=True)
            status(progress,'preparing',clip=number,total=len(selection['matches']),file=match['file'],split=match['split'])
            print(f"Clip {number}/{len(selection['matches'])} [{match['split']}]: {match['file']}",flush=True)
            info = read_json(directory/'shard.json')
            if info and digest(directory/'features.pt')!=info['payload_sha256']:
                raise ValueError('completed shard was changed; preserve evidence and choose new data directory')
            try:
                if not info:
                    replay = ROOT/match['file']
                    if digest(replay)!=match['replay_sha256']: raise ValueError('source replay changed')
                    # Reuse the already audited pilot clips without rendering them again.
                    known = {'c13e36c0f079200b6f00e2b3bef22ffe1165cde23797325218509718d794b40f':
                                ('learning-timing-v1/video-v2','learning-timing-v1/labels.json'),
                             '35f1c56f2c5ac6ceeb74ff5144d923443bf34251d4404802408c28e577a48ae7':
                                ('learning-heldout-v1/video','learning-heldout-v1/labels-for-scoring.json')}
                    if match['replay_sha256'] in known:
                        video_name, labels_name = known[match['replay_sha256']]
                        video, labels = ROOT/'.docker-state/local'/video_name,ROOT/'.docker-state/local'/labels_name
                    else:
                        reusable = []
                        for receipt in sorted(directory.glob('attempt-*/capture/capture.json')):
                            old = read_json(receipt)
                            if (old.get('capture_passed') is True and old.get('source_replay_sha256')==match['replay_sha256']
                                    and old.get('wanted_interval')==[-60,config['prepare_last_frame']]):
                                index = read_json(receipt.parent/'capture-index.json')
                                if all(digest(receipt.parent/'user/Dump/Frames'/r['capture_image'])==r['capture_image_sha256'] for r in index):
                                    reusable.append(receipt.parent)
                        attempt = directory/f'attempt-{len(list(directory.glob("attempt-*")))+1:03d}'
                        attempt.mkdir(); log = attempt/'preparation.log'
                        capture = attempt/'capture'; video = attempt/'video'; labels = attempt/'labels.json'
                        if reusable:
                            capture = reusable[-1]
                            atomic_json(attempt/'capture-reference.json',{'capture':str(capture.relative_to(ROOT)),
                                'receipt_sha256':digest(capture/'capture.json'),'policy':'reuse successful capture; rerun all preparation audits'})
                        else:
                            run(['xvfb-run','-a','-s','-screen 0 1024x768x24',sys.executable,'scripts/capture_signed_frames.py',
                                '--dolphin',ROOT/config['playback'],'--iso',ROOT/config['iso'],'--replay',replay,
                                '--osd-calibration',ROOT/config['osd_calibration'],'--first',-60,'--last',config['prepare_last_frame'],
                                '--per-step-log-association','--timeout',1800,'--output',capture],log)
                        run([sys.executable,'scripts/prepare_signed_video.py','--replay',replay,'--capture',capture,
                            '--timer-calibration',ROOT/config['timer_calibration'],'--phase-reference',ROOT/config['phase_reference'],
                            '--output',video],log)
                        with labels.open('x') as handle:
                            subprocess.run(['node','tools/slippi-parser/export-training.cjs',str(replay),'-60',str(config['prepare_last_frame'])],
                                stdout=handle,check=True,cwd=ROOT)
                    info = cache_clip(video,labels,directory,config['context_frames'],device)
                shards.append({**info,'split':match['split'],'group':match['group'],
                    'payload':str((directory/'features.pt').relative_to(output))})
            except Exception as error:
                failures.append({'file':match['file'],'split':match['split'],'error':str(error)})
                atomic_json(directory/'last-failure.json',failures[-1]); print(failures[-1],flush=True)
        if failures: raise ValueError(f'{len(failures)} selected clips failed; retained failures; rerun prepare to retry')
        result = {'schema':1,'kind':'vision-feature-dataset','context_frames':config['context_frames'],
            'slot_characters':[2,20],'stage':31,'selection_sha256':digest(output/'selection.json'),
            'selection':'selection.json','split_plan':os.path.relpath(plan_path,output),
            'split_plan_sha256':digest(plan_path),'shards':shards,'test_matches_opened':0,
            'phase_policy':'same-key zero phase; independently audited pilot plus explicit transferred references for new captures',
            'native_vi_adapter_verified':False,'generalization_established':False}
        if any(s['windows']<=0 for s in shards): raise ValueError('insufficient temporal context')
        atomic_json(output/'dataset.json',result)
        status(progress,'ready',shards=len(shards),windows={s:sum(x['windows'] for x in shards if x['split']==s) for s in ('train','validation')})
    except BaseException as error:
        status(progress,'failed',error=str(error)); raise


if __name__ == '__main__': main()
