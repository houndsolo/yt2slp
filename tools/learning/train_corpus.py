"""Resumable expanded-corpus training; old trainer/checkpoints remain unchanged."""
import argparse
from pathlib import Path
import signal
import time

from train_smoke import torch
import torchvision
from baseline import TemporalProposal, proposal_loss
from corpus_data import CorpusStore
from manage import validate_config
from runtime_files import ROOT, atomic_json, digest, read_json, status
from train import evaluate, load_checkpoint, save_checkpoint


def contract(config,dataset,device):
    files=('train_corpus.py','corpus_data.py','baseline.py','train.py','stream_data.py')
    return {'kind':'physical-port-fox-corpus-v3','dataset_sha256':digest(dataset),
        'torch_version':str(torch.__version__),'torchvision_version':str(torchvision.__version__),'device':device,
        'slot_mapping':'ascending-physical-ports','code':{**{f:digest(Path(__file__).with_name(f)) for f in files},
            'corpus.py':digest(ROOT/'src/yt2slp/corpus.py')},
        'hyperparameters':{k:config[k] for k in ('context_frames','hidden_size','batch_size','learning_rate','seed')}}


def train(config,run,device_name='cuda',max_steps=None):
    import json
    validate_config(config); run.mkdir(parents=True,exist_ok=True)
    progress=run/'status.json'; status(progress,'loading',step=read_json(run/'latest.json',{}).get('step',0))
    stop=[None]
    def request(signum,frame): stop[0]='stop'
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,request)
    torch.set_num_threads(config['threads']); torch.manual_seed(config['seed'])
    device=torch.device(device_name)
    if device.type=='cuda':
        if not torch.cuda.is_available(): raise ValueError('CUDA unavailable; no fallback')
        torch.cuda.set_per_process_memory_fraction(config['gpu_memory_fraction']); torch.cuda.manual_seed_all(config['seed'])
    dataset=ROOT/config['data_directory']/'dataset.json'; expected=contract(config,dataset,device_name)
    training=CorpusStore(dataset,'train'); validation=CorpusStore(dataset,'validation')
    if training.dataset['context_frames']!=config['context_frames']: raise ValueError('corpus/context mismatch')
    network=TemporalProposal(3072,config['hidden_size']).to(device)
    optimizer=torch.optim.AdamW(network.parameters(),lr=config['learning_rate'])
    weights=training.button_weights().to(device); sampler=torch.Generator().manual_seed(config['seed']+1)
    step=0; best_score=None; latest_validation=None; latest_loss=None
    restored=load_checkpoint(run,expected)
    if restored:
        network.load_state_dict(restored['model'],strict=True); optimizer.load_state_dict(restored['optimizer'])
        sampler.set_state(restored['sampler_rng']); torch.set_rng_state(restored['torch_rng'])
        if device.type=='cuda': torch.cuda.set_rng_state_all(restored['cuda_rng'])
        step=restored['step']; best_score=restored['best_score']; latest_validation=restored['validation']
    limit=config['max_steps'] if max_steps is None else max_steps
    if limit<step: raise ValueError('total step limit precedes saved checkpoint')
    atomic_json(run/'contract.json',expected); started=time.monotonic(); start_step=step
    def checkpoint(best=False):
        return save_checkpoint(run,{'schema':1,'kind':'resumable-vision-corpus-trainer','step':step,'contract':expected,
            'model':network.state_dict(),'optimizer':optimizer.state_dict(),'sampler_rng':sampler.get_state(),
            'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all() if device.type=='cuda' else [],
            'best_score':best_score,'validation':latest_validation},best)
    def report(state,**more):
        return status(progress,state,step=step,max_steps=limit,train_windows=training.total,
            validation_windows=validation.total,training_loss=latest_loss,best_validation_event_f1=best_score,
            latest_validation=latest_validation,steps_per_second=(step-start_step)/max(.001,time.monotonic()-started),
            device=device_name,**more)
    report('running',resumed_from_step=step)
    while True:
        wanted=stop[0] or read_json(run/'control.json',{}).get('command')
        if wanted in ('pause','stop'):
            pointer=checkpoint(); report('paused' if wanted=='pause' else 'stopped',checkpoint=pointer); return
        if step>=limit: checkpoint(); report('completed'); return
        indices=torch.randint(training.total,(config['batch_size'],),generator=sampler).tolist()
        features,targets=training.batch(indices); optimizer.zero_grad(set_to_none=True)
        loss,_=proposal_loss(network(features.to(device)),{k:v.to(device) for k,v in targets.items()},weights)
        if not torch.isfinite(loss): raise ValueError('non-finite loss')
        loss.backward(); torch.nn.utils.clip_grad_norm_(network.parameters(),5); optimizer.step()
        step+=1; latest_loss=float(loss.detach())
        if step%config['evaluate_every']==0:
            report('evaluating'); latest_validation=evaluate(network,validation,weights,device,config['batch_size'])
            score=latest_validation['event_f1_mean']; improved=score is not None and (best_score is None or score>best_score)
            if improved: best_score=score
            pointer=checkpoint(improved)
            with (run/'metrics.ndjson').open('a') as handle:
                handle.write(json.dumps({'step':step,'validation':latest_validation,'checkpoint':pointer,'unix':time.time()})+'\n')
            print(json.dumps({'step':step,'validation':latest_validation}),flush=True)
        elif step%config['checkpoint_every']==0: checkpoint()
        if step%config['log_every']==0: print(json.dumps(report('running')),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True); parser.add_argument('--steps',type=int)
    parser.add_argument('--device',choices=('cpu','cuda'),default='cuda')
    args=parser.parse_args(); config=read_json(args.config); run=ROOT/config['run_directory']
    try:
        if args.steps is not None and args.steps<1: raise ValueError('positive total steps required')
        train(config,run,args.device,args.steps)
    except BaseException as error:
        previous=read_json(run/'status.json',{}); previous.pop('state',None); previous.pop('updated_unix',None)
        previous.pop('error',None); status(run/'status.json','failed',**previous,error=str(error)); raise


if __name__=='__main__': main()
