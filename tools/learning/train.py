"""Resumable temporal-head training on frozen image features, with safe exits."""
import argparse
import json
import os
from pathlib import Path
import signal
import time

from train_smoke import torch  # Also sets a UID-safe Torch cache before importing torchvision.
import torchvision
from baseline import TemporalProposal, binary_metrics, proposal_loss, state_metrics
from runtime_files import ROOT, atomic_json, digest, read_json, status
from stream_data import WindowStore
from manage import validate_config


def contract(config, dataset, device):
    return {'dataset_sha256':digest(dataset),'torch_version':str(torch.__version__),
        'torchvision_version':str(torchvision.__version__),'device':device,
        'code':{p.name:digest(p) for p in (Path(__file__),Path(__file__).with_name('baseline.py'),Path(__file__).with_name('stream_data.py'))},
        'hyperparameters':{k:config[k] for k in ('context_frames','hidden_size','batch_size','learning_rate','seed')}}


def save_checkpoint(run, payload, best=False):
    folder = run/'checkpoints'; folder.mkdir(parents=True,exist_ok=True)
    filename = f'step-{payload["step"]:09d}-{time.time_ns()}.pt'; target = folder/filename
    temporary = target.with_suffix('.tmp')
    with temporary.open('wb') as handle:
        torch.save(payload,handle); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary,target)
    pointer = {'file':str(target.relative_to(run)),'sha256':digest(target),'step':payload['step']}
    previous = read_json(run/'latest.json')
    atomic_json(run/'latest.json',pointer)
    if best: atomic_json(run/'best.json',pointer)
    kept = {pointer['file']}
    if previous: kept.add(previous['file'])
    selected = read_json(run/'best.json')
    if selected: kept.add(selected['file'])
    for path in folder.glob('step-*.pt'):
        if str(path.relative_to(run)) not in kept: path.unlink()
    return pointer


def load_checkpoint(run, expected):
    pointer = read_json(run/'latest.json')
    if not pointer: return None
    path = run/pointer['file']
    if digest(path)!=pointer['sha256']: raise ValueError('checkpoint checksum differs; preserved previous generations for recovery')
    payload = torch.load(path,map_location='cpu',weights_only=True)
    if payload['contract']!=expected: raise ValueError('checkpoint dataset, runtime, source or hyperparameters changed; use a new run')
    if payload['step']!=pointer['step']: raise ValueError('checkpoint step differs from committed pointer')
    return payload


def evaluate(network, store, weights, device, batch_size):
    network.eval(); buttons = {}; states = {}; neutral = {}; components = {}; counts = {}
    with torch.no_grad():
        for start in range(0,store.total,batch_size):
            features,targets = store.batch(range(start,min(start+batch_size,store.total)))
            targets = {k:v.to(device) for k,v in targets.items()}
            prediction = network(features.to(device))
            _, losses = proposal_loss(prediction,targets,weights)
            for key,loss in losses.items():
                n = int(targets[key+'_mask'].sum()); counts[key] = counts.get(key,0)+n
                components[key] = components.get(key,0.)+float(loss)*n
            for head,metric in binary_metrics(prediction,targets).items():
                aggregate = buttons.setdefault(head,dict(tp=0,fp=0,fn=0))
                for key in aggregate: aggregate[key] += metric[key]
            metric = state_metrics(prediction,targets)
            for axis,name in enumerate(('stick_x','stick_y','cstick_x','cstick_y','trigger')):
                neutral['axis_'+name] = neutral.get('axis_'+name,0)+int(((targets['axes'][:,:,axis]==(0 if name=='trigger' else 8)) & targets['axes_mask'][:,:,axis]).sum())
            for name,value in {'action':metric['action'],'airborne':metric['airborne'],
                               **{'axis_'+k:v for k,v in metric['axes'].items()}}.items():
                aggregate = states.setdefault(name,dict(compared=0,correct=0))
                for key in aggregate: aggregate[key] += value[key]
    for metric in buttons.values():
        tp,fp,fn = (metric[k] for k in ('tp','fp','fn'))
        metric['f1'] = 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None
        metric['positive_labels'] = tp+fn
        metric['all_released_baseline_f1'] = 0. if tp+fn else None
    for name,metric in states.items():
        metric['accuracy'] = metric['correct']/metric['compared'] if metric['compared'] else None
        if name in neutral: metric['neutral_baseline_accuracy'] = neutral[name]/metric['compared'] if metric['compared'] else None
    f1 = [m['f1'] for m in buttons.values() if m['f1'] is not None]
    network.train()
    return {'button_metrics':buttons,'state_metrics':states,
        'loss':sum(components[k]/max(counts[k],1) for k in components),
        'event_f1_mean':sum(f1)/len(f1) if f1 else None,'windows':store.total}


def train(config,run,device_name='cuda',max_steps=None):
    validate_config(config)
    run.mkdir(parents=True,exist_ok=True); progress = run/'status.json'
    status(progress,'loading',step=read_json(run/'latest.json',{}).get('step',0))
    command = [None]
    def request_stop(signum,frame): command[0] = 'stop'
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,request_stop)
    torch.set_num_threads(config['threads']); torch.manual_seed(config['seed'])
    device = torch.device(device_name)
    if device.type=='cuda':
        if not torch.cuda.is_available(): raise ValueError('CUDA requested but unavailable; no fallback')
        torch.cuda.set_per_process_memory_fraction(config['gpu_memory_fraction'])
        torch.cuda.manual_seed_all(config['seed'])
    dataset = ROOT/config['data_directory']/'dataset.json'
    expected = contract(config,dataset,device_name)
    training = WindowStore(dataset,'train'); validation = WindowStore(dataset,'validation')
    if training.dataset['context_frames']!=config['context_frames']: raise ValueError('dataset/context mismatch')
    weights = training.button_weights().to(device)
    network = TemporalProposal(3072,config['hidden_size']).to(device)
    optimizer = torch.optim.AdamW(network.parameters(),lr=config['learning_rate'])
    sampler = torch.Generator().manual_seed(config['seed']+1)
    step = 0; best_score = None; last_validation = None
    restored = load_checkpoint(run,expected)
    if restored:
        network.load_state_dict(restored['model'],strict=True); optimizer.load_state_dict(restored['optimizer'])
        sampler.set_state(restored['sampler_rng']); torch.set_rng_state(restored['torch_rng'])
        if device.type=='cuda': torch.cuda.set_rng_state_all(restored['cuda_rng'])
        step = restored['step']; best_score = restored['best_score']; last_validation = restored['validation']
    limit = config['max_steps'] if max_steps is None else max_steps
    if limit<step: raise ValueError('requested total step limit precedes saved checkpoint')
    atomic_json(run/'contract.json',expected)
    started = time.monotonic(); start_step = step; latest_loss = None
    def checkpoint(best=False):
        return save_checkpoint(run,{'schema':1,'kind':'resumable-vision-trainer','step':step,'contract':expected,
            'model':network.state_dict(),'optimizer':optimizer.state_dict(),
            'sampler_rng':sampler.get_state(),'torch_rng':torch.get_rng_state(),
            'cuda_rng':torch.cuda.get_rng_state_all() if device.type=='cuda' else [],
            'best_score':best_score,'validation':last_validation},best=best)
    def report(state,**more):
        return status(progress,state,step=step,max_steps=limit,train_windows=training.total,
            validation_windows=validation.total,training_loss=latest_loss,best_validation_event_f1=best_score,
            latest_validation=last_validation,steps_per_second=(step-start_step)/max(.001,time.monotonic()-started),
            device=device_name,**more)
    report('running',resumed_from_step=step)
    while True:
        wanted = command[0] or read_json(run/'control.json',{}).get('command')
        if wanted in ('pause','stop'):
            pointer = checkpoint(); report('paused' if wanted=='pause' else 'stopped',checkpoint=pointer)
            return
        if step>=limit:
            checkpoint(); report('completed'); return
        indices = torch.randint(training.total,(config['batch_size'],),generator=sampler).tolist()
        features,targets = training.batch(indices)
        optimizer.zero_grad(set_to_none=True)
        loss,_ = proposal_loss(network(features.to(device)),{k:v.to(device) for k,v in targets.items()},weights)
        if not torch.isfinite(loss): raise ValueError('non-finite training loss')
        loss.backward(); torch.nn.utils.clip_grad_norm_(network.parameters(),5); optimizer.step()
        step += 1; latest_loss = float(loss.detach())
        if step%config['evaluate_every']==0:
            report('evaluating'); last_validation = evaluate(network,validation,weights,device,config['batch_size'])
            score = last_validation['event_f1_mean']; improved = score is not None and (best_score is None or score>best_score)
            if improved: best_score = score
            pointer = checkpoint(best=improved)
            with (run/'metrics.ndjson').open('a') as handle:
                handle.write(json.dumps({'step':step,'validation':last_validation,'checkpoint':pointer,'unix':time.time()})+'\n')
            print(json.dumps({'step':step,'validation':last_validation}),flush=True)
        elif step%config['checkpoint_every']==0: checkpoint()
        if step%config['log_every']==0:
            print(json.dumps(report('running')),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/vision-v100.json')
    parser.add_argument('--run',type=Path)
    parser.add_argument('--steps',type=int,help='total optimizer-step limit, including resumed steps')
    parser.add_argument('--device',choices=('cpu','cuda'),default='cuda')
    args = parser.parse_args(); config = read_json(args.config); run = args.run or ROOT/config['run_directory']
    try:
        if args.steps is not None and args.steps<1: raise ValueError('positive total step limit required')
        train(config,run,args.device,args.steps)
    except BaseException as error:
        old = read_json(run/'status.json',{}); old.pop('state',None); old.pop('updated_unix',None); old.pop('error',None)
        status(run/'status.json','failed',**old,error=str(error)); raise


if __name__ == '__main__': main()
