"""Review a saved training checkpoint on prepared validation videos.

Image-only inference completes before scoring labels are opened. This produces
source footage/controller panels, not simulated gameplay or a generated replay.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

from runtime_files import ROOT, atomic_json, digest, read_json, status
from train import contract
from train_smoke import torch, encode_images
from baseline import TemporalProposal
from predict import decode_batch
from stream_data import WindowStore
from yt2slp.model_contract import slot_ports, validate_image_view
from yt2slp.prediction_scoring import score_predictions


def bound_file(candidates, expected):
    found = [p for p in candidates if p.is_file() and digest(p)==expected]
    if not found: raise ValueError('required identity-bound review artifact is missing')
    return found[0]


def snapshot(run, output, choice, expected):
    pointer = read_json(run/(choice+'.json'))
    if not pointer: raise ValueError(f'no {choice} checkpoint; train until a checkpoint is saved')
    original = run/pointer['file']
    if digest(original)!=pointer['sha256']: raise ValueError('checkpoint checksum changed')
    copy = output/'model-snapshot.pt'; shutil.copy2(original,copy)
    if digest(copy)!=pointer['sha256']: raise ValueError('checkpoint changed during snapshot copy')
    payload = torch.load(copy,map_location='cpu',weights_only=True)
    if payload['contract']!=expected or payload['step']!=pointer['step']:
        raise ValueError('checkpoint runtime, dataset, code or step mismatch')
    atomic_json(output/'snapshot.json',{'choice':choice,**pointer,'local_snapshot':copy.name,
        'policy':'immutable copied checkpoint; review never updates weights or optimizer'})
    return payload,pointer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/vision-v100.json')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--snapshot',choices=('latest','best'),default='latest')
    args = parser.parse_args(); config = read_json(args.config); output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=False); progress = output/'status.json'
    try:
        status(progress,'loading',snapshot=args.snapshot)
        if not torch.cuda.is_available(): raise ValueError('CUDA unavailable; no silent CPU fallback')
        torch.set_num_threads(config['threads']); torch.cuda.set_per_process_memory_fraction(config['gpu_memory_fraction'])
        dataset_path = ROOT/config['data_directory']/'dataset.json'
        store = WindowStore(dataset_path,'validation')  # Checks identities/splits without loading target tensors.
        payload,pointer = snapshot(ROOT/config['run_directory'],output,args.snapshot,contract(config,dataset_path,'cuda'))
        network = TemporalProposal(3072,config['hidden_size']).cuda()
        network.load_state_dict(payload['model'],strict=True); network.eval()
        clips = []
        for number,shard in enumerate(store.shards,1):
            directory = output/f'validation-{number:02d}-{shard["replay_sha256"][:8]}'
            directory.mkdir(); source = (dataset_path.parent/shard['payload']).parent
            view_path = bound_file(source.glob('images-*.json'),shard['image_view_sha256'])
            view = read_json(view_path); validate_image_view(view,config['context_frames'])
            if view['replay_sha256']!=shard['replay_sha256']: raise ValueError('view replay identity mismatch')
            ports = slot_ports({'stage':31,'slot_characters':[2,20]},view['settings'])
            if (digest(Path(__file__).with_name('train_smoke.py'))!=shard['preprocessing_sha256']
                    or digest(Path(torch.hub.get_dir())/'checkpoints/resnet18-f37072fd.pth')!=shard['encoder_weights_sha256']):
                raise ValueError('frozen image preprocessing/encoder identity differs')
            status(progress,'predicting',clip=number,total=len(store.shards),checkpoint_step=payload['step'])
            features = encode_images(view_path,view,16,torch.device('cuda'))
            half = config['context_frames']//2; centers = list(range(half,len(features)-half)); rows = []
            with torch.no_grad():
                for start in range(0,len(centers),config['batch_size']):
                    batch = centers[start:start+config['batch_size']]
                    windows = torch.stack([features[i-half:i+half+1] for i in batch]).cuda()
                    prediction = {k:v.cpu() for k,v in network(windows).items()}
                    rows.extend(decode_batch(prediction,[view['frames'][i] for i in batch],ports,[2,20]))
            predictions = {'schema':1,'kind':'frozen-image-controller-predictions',
                'replay_sha256':view['replay_sha256'],'view_sha256':digest(view_path),
                'checkpoint_sha256':pointer['sha256'],'checkpoint_step':payload['step'],
                'model_descriptor_sha256':digest(output/'snapshot.json'),'training_regression':False,
                'settings':view['settings'],'slot_ports':ports,'slot_characters':[2,20],
                'prediction_interval':[rows[0]['frame'],rows[-1]['frame']],
                'context_frames':config['context_frames'],'rows':rows,
                'policy':'validation-only; pixels/known roster; fixed zero-logit threshold; no label input, lag fit or optimizer update',
                'native_vi_adapter_verified':False,'generated_replay_validated':False}
            predictions_path = directory/'predictions.json'; atomic_json(predictions_path,predictions)
            # Predictions are frozen before locating or opening the scoring answers.
            candidates = list(source.glob('attempt-*/labels.json'))+[
                ROOT/'.docker-state/local/learning-heldout-v1/labels-for-scoring.json']
            labels_path = bound_file(candidates,shard['labels_sha256']); labels = read_json(labels_path)
            score = score_predictions(predictions,labels)
            score.update(predictions_sha256=digest(predictions_path),labels_sha256=digest(labels_path))
            atomic_json(directory/'score.json',score)
            status(progress,'rendering',clip=number,total=len(store.shards),checkpoint_step=payload['step'])
            subprocess.run([sys.executable,'scripts/render_prediction_review.py','--view',str(view_path),
                '--predictions',str(predictions_path),'--labels',str(labels_path),'--output',str(directory/'video')],check=True,cwd=ROOT)
            mkv = directory/'video/prediction-review.mkv'; mp4 = directory/'prediction-review.mp4'
            subprocess.run(['ffmpeg','-v','error','-n','-i',str(mkv),'-c:v','libx264','-crf','18',
                '-preset','fast','-pix_fmt','yuv420p','-movflags','+faststart',str(mp4)],check=True)
            clips.append({'split':'validation','replay_sha256':view['replay_sha256'],
                'mp4':str(mp4.relative_to(output)),'mp4_sha256':digest(mp4),
                'mkv':str(mkv.relative_to(output)),'mkv_sha256':digest(mkv),
                'frames':len(view['frames']),'button_metrics':score['button_metrics']})
            print(mp4,flush=True)
        atomic_json(output/'review.json',{'schema':1,'kind':'saved-model-controller-review',
            'checkpoint':pointer,'checkpoint_choice':args.snapshot,'clips':clips,
            'test_matches_opened':0,'generated_gameplay':False,'training_updated':False})
        status(progress,'complete',checkpoint_step=payload['step'],clips=clips)
    except BaseException as error:
        status(progress,'failed',error=str(error)); raise


if __name__=='__main__': main()
