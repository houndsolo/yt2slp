"""Host-side controls for detached server-local preparation and training."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from runtime_files import ROOT, atomic_json, read_json

NAMES = {'training':'yt2slp-vision-trainer','preparation':'yt2slp-vision-prepare','review':'yt2slp-vision-review'}
ROLES = {'training':'vision-trainer','preparation':'vision-prepare','review':'vision-review'}


def inspect(kind):
    result = subprocess.run(['docker','inspect',NAMES[kind]],capture_output=True,text=True)
    if result.returncode: return None
    container = json.loads(result.stdout)[0]
    if container['Config'].get('Labels',{}).get('org.yt2slp.role')!=ROLES[kind]:
        raise ValueError('container name belongs to another application; left untouched')
    return container['State']


def validate_config(config):
    if not isinstance(config,dict) or config.get('schema')!=1 or not re.fullmatch(r'GPU-[0-9a-fA-F-]{36}|[0-9]+',config['gpu']):
        raise ValueError('versioned config with exactly one GPU required')
    for key in ('python','data_directory','run_directory','split_plan','iso','playback','osd_calibration','timer_calibration','phase_reference'):
        path = Path(config[key])
        # venv Python deliberately symlinks to the container's system interpreter.
        checked = Path(os.path.abspath(ROOT/path)) if key=='python' else (ROOT/path).resolve()
        if path.is_absolute() or not checked.is_relative_to(ROOT): raise ValueError(f'{key} must stay in checkout')
    bounds = {'context_frames':(3,121),'batch_size':(1,256),'hidden_size':(16,512),'threads':(1,32),
        'max_steps':(1,1000000000),'checkpoint_every':(1,1000000),'evaluate_every':(1,1000000),'log_every':(1,1000000),
        'train_matches':(2,1000),'validation_matches':(1,1000),'prepare_last_frame':(180,1800)}
    for key,(low,high) in bounds.items():
        if type(config[key]) is not int or not low<=config[key]<=high: raise ValueError(f'invalid {key}')
    if config['context_frames']%2!=1 or not 0<config['learning_rate']<1 or not 0<config['gpu_memory_fraction']<=1:
        raise ValueError('invalid context, learning rate or memory cap')


def docker_command(config,config_path,kind,steps=None):
    image = config['training_image'] if kind=='training' else config['render_image']
    command = ['docker','run','--detach','--name',NAMES[kind],'--init','--restart=no','--shm-size=512m','--network=none',
        '--user',f'{os.getuid()}:{os.getgid()}', '--mount',f'type=bind,src={ROOT},dst=/work',
        '--workdir','/work','--gpus','device='+config['gpu'],
        '--label','org.yt2slp.role='+ROLES[kind],
        '-e','NVIDIA_DRIVER_CAPABILITIES=compute,utility','-e','PYTHONUNBUFFERED=1','-e','PYTHONPATH=/work/src',
        '-e','TORCH_HOME=/work/.docker-state/cache/torch',image,config['python'],
        {'preparation':'tools/learning/prepare_dataset.py','training':'tools/learning/train.py','review':'tools/learning/review_run.py'}[kind],
        '--config',str(config_path.relative_to(ROOT))]
    if steps is not None: command += ['--steps',str(steps)]
    return command


def launch(config,path,kind,steps=None,best=False):
    for other_kind in NAMES:
        if other_kind==kind: continue
        other = inspect(other_kind)
        if other and other['Running']: raise ValueError(f'wait for or stop {other_kind} before sharing its GPU/dataset')
    old = inspect(kind)
    if old and old['Running']:
        print(f'{kind} already running'); return
    if kind=='training':
        if not (ROOT/config['data_directory']/'dataset.json').is_file(): raise ValueError('dataset not ready; run prepare, then status')
        run = ROOT/config['run_directory']; run.mkdir(parents=True,exist_ok=True)
        previous = read_json(run/'latest.json')
        if previous and previous['step']>=(steps or config['max_steps']):
            print(f"Already saved step {previous['step']:,}; use start --steps with a larger total limit.")
            return
        atomic_json(run/'control.json',{'command':'run','requested_unix':time.time()})
        atomic_json(run/'launch.json',{'max_steps':steps or config['max_steps'],'requested_unix':time.time()})
    required = ('python','iso','playback','osd_calibration','timer_calibration','phase_reference','split_plan') if kind=='preparation' else ('python',)
    for key in required:
        candidate = ROOT/config[key]
        if not (candidate.is_file() or (key=='python' and candidate.is_symlink())): raise ValueError(f'missing {key}; see training-control.md')
    command = docker_command(config,path,kind,steps)
    if kind=='review':
        output = ROOT/config['run_directory']/'reviews'/f'review-{time.time_ns()}'
        atomic_json(output.parent/'latest.json',{'directory':str(output.relative_to(ROOT))})
        command += ['--output',str(output.relative_to(ROOT)),'--snapshot','best' if best else 'latest']
    if old: subprocess.run(['docker','rm',NAMES[kind]],check=True,stdout=subprocess.DEVNULL)
    result = subprocess.run(command,check=True,capture_output=True,text=True)
    print(f'{kind} started ({result.stdout.strip()[:12]}). You can disconnect SSH now.')


def request(config,command):
    state = inspect('training')
    if not state or not state['Running']:
        print('No training worker is running; checkpoint is retained.'); return
    run = ROOT/config['run_directory']
    atomic_json(run/'control.json',{'command':command,'requested_unix':time.time()})
    print(f'{command} requested; waiting for checkpoint and container exit...',flush=True)
    deadline = time.monotonic()+55
    while time.monotonic()<deadline:
        state = inspect('training')
        if not state or not state['Running']:
            info = read_json(run/'status.json',{})
            print(f"{info.get('state','exited')}; saved step {info.get('step','?')}")
            if info.get('error'): print(info['error'])
            return
        time.sleep(.3)
    print('Request remains pending; use status. Do not remove the container while it saves.')


def show_status(config):
    for kind,folder,filename in (('preparation',config['data_directory'],'preparation-status.json'),
                                 ('training',config['run_directory'],'status.json')):
        state = inspect(kind); info = read_json(ROOT/folder/filename,{})
        running = bool(state and state['Running']); label = info.get('state','not started')
        if running and not info: label = 'starting'
        if not running and label in ('running','evaluating','loading','preparing'): label = 'interrupted'
        print(f'{kind.capitalize()}: {label} (container {"running" if running else "not running"})')
        if kind=='preparation' and info.get('clip'): print(f"  Clip {info['clip']}/{info['total']}: {info['file']}")
        if kind=='training' and 'step' in info:
            print(f"  Step {info['step']:,} / {info.get('max_steps',0):,}; loss {info.get('training_loss')}; {info.get('steps_per_second',0):.1f} steps/sec")
            if info.get('latest_validation'):
                metrics = info['latest_validation']['button_metrics']
                print('  Validation F1: '+', '.join(f"{k}={v['f1']}" for k,v in metrics.items()))
                print(f"  Best validation event F1 mean: {info.get('best_validation_event_f1')}")
        if info.get('error'): print('  '+info['error'])
    pointer = read_json(ROOT/config['run_directory']/'latest.json')
    if pointer: print(f"Latest checkpoint (step {pointer['step']:,}):",str(ROOT/config['run_directory']/pointer['file']))
    review = read_json(ROOT/config['run_directory']/'reviews/latest.json')
    if review:
        output = ROOT/review['directory']; info = read_json(output/'status.json',{})
        state = inspect('review'); running = bool(state and state['Running'])
        label = info.get('state','starting' if running else 'not started')
        if not running and label in ('loading','predicting','rendering'): label = 'interrupted'
        print(f'Review: {label}; {output}')
        for clip in info.get('clips',[]): print('  Video:',output/clip['mp4'])


def doctor(config):
    for key in ('python','iso','playback','osd_calibration','timer_calibration','phase_reference','split_plan'):
        candidate = ROOT/config[key]
        present = candidate.is_file() or (key=='python' and candidate.is_symlink())
        print(f'{key}: {"OK" if present else "MISSING"} ({config[key]})')
    for key in ('training_image','render_image'):
        result = subprocess.run(['docker','image','inspect',config[key]],capture_output=True)
        print(f'{key}: {"OK" if result.returncode==0 else "MISSING"}')
    subprocess.run(['nvidia-smi','--query-gpu=index,name,uuid,memory.free','--format=csv,noheader'],check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',nargs='?',choices=('start','resume','pause','stop','status','logs','prepare','stop-preparing','doctor','review'))
    parser.add_argument('--config',type=Path,default=ROOT/'configs/vision-v100.json')
    parser.add_argument('--steps',type=int,help='total step limit, including previous steps')
    parser.add_argument('--follow',action='store_true',help='follow logs; Ctrl-C only closes the log viewer')
    parser.add_argument('--preparation',action='store_true',help='show preparation logs instead of training logs')
    parser.add_argument('--review',action='store_true',help='show review logs instead of training logs')
    parser.add_argument('--best',action='store_true',help='review the best validation checkpoint rather than latest')
    args = parser.parse_args(); path = args.config.resolve()
    if not path.is_relative_to(ROOT): parser.error('config must be in checkout')
    config = read_json(path); validate_config(config)
    if args.steps is not None and not 1<=args.steps<=1000000000: parser.error('positive bounded total steps required')
    if not args.command:
        menu = {'1':'start','2':'pause','3':'resume','4':'stop','5':'status','6':'logs','7':'prepare','8':'doctor','9':'review'}
        while True:
            print('\n1 Start training   2 Pause   3 Resume   4 Stop\n5 Status   6 Logs   7 Prepare data   8 Check setup\n9 Review latest model on validation clips   0 Quit')
            choice = input('Choose: ').strip()
            if choice=='0': return
            if choice in menu:
                subprocess.run([sys.executable,__file__,menu[choice],'--config',str(path)],check=False)
        return
    if args.command=='logs':
        command = ['docker','logs','--tail','50']
        if args.follow: command.append('--follow')
        if args.preparation and args.review: parser.error('choose preparation or review logs')
        os.execvp('docker',command+[NAMES['preparation' if args.preparation else 'review' if args.review else 'training']])
    lock_path = ROOT/'.docker-state/local/vision-training/controller.lock'; lock_path.parent.mkdir(parents=True,exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.command in ('start','resume'): launch(config,path,'training',args.steps)
        elif args.command=='prepare': launch(config,path,'preparation')
        elif args.command in ('pause','stop'): request(config,args.command)
        elif args.command=='status': show_status(config)
        elif args.command=='doctor': doctor(config)
        elif args.command=='review':
            request(config,'pause')
            launch(config,path,'review',best=args.best)
        elif args.command=='stop-preparing':
            state = inspect('preparation')
            if state and state['Running']: subprocess.run(['docker','stop','-t','10',NAMES['preparation']],check=True)
            print('Preparation stopped; completed shards and failed/incomplete attempts retained.')


if __name__ == '__main__':
    try: main()
    except (ValueError,KeyError,FileNotFoundError,BlockingIOError,subprocess.CalledProcessError) as error:
        print('yt2slp training: '+str(error),file=sys.stderr); sys.exit(1)
