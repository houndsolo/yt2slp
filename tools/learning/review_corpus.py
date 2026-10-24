"""Review a saved corpus model on a fixed, balanced validation sample.

Original images are encoded before scoring labels are opened. Output is source
footage plus controller predictions, not reconstructed gameplay.
"""
import argparse
from pathlib import Path
import subprocess
import sys

from train_smoke import torch, encode_images
from baseline import TemporalProposal
from corpus_data import CorpusStore
from predict import decode_batch
from review_run import snapshot
from runtime_files import ROOT, atomic_json, digest, read_json, status
from train_corpus import contract
from yt2slp import button_decoder
from yt2slp.corpus import corpus_ports
from yt2slp.model_contract import validate_image_view
from yt2slp.prediction_scoring import score_predictions


def review_selection(shards,maximum):
    buckets={}
    for shard in sorted(shards,key=lambda s:s['clip_id']): buckets.setdefault(tuple(sorted(shard['slot_characters'])),[]).append(shard)
    chosen=[]
    while any(buckets.values()) and len(chosen)<maximum:
        for key in sorted(buckets):
            if buckets[key] and len(chosen)<maximum: chosen.append(buckets[key].pop(0))
    return chosen


def aggregate_comparisons(clips):
    result = {'clips': len(clips), 'player_frames': sum(c['comparison']['player_frames'] for c in clips)}
    for mode in ('raw', 'constrained'):
        metrics = {}
        for head in button_decoder.HEADS:
            counts = {name: sum(c['comparison'][mode]['button_metrics'][head][name] for c in clips)
                      for name in ('tp', 'fp', 'fn')}
            denominator = 2*counts['tp']+counts['fp']+counts['fn']
            metrics[head] = {**counts, 'f1': 2*counts['tp']/denominator if denominator else None}
        result[mode] = {'button_metrics': metrics,
            'invalid_button_frames': sum(c['comparison'][mode]['consistency']['invalid_button_frames'] for c in clips)}
    result['scope'] = 'fixed development-validation review clips only; not the entire validation corpus or final test'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--snapshot',choices=('latest','best'),default='latest')
    parser.add_argument('--max-clips',type=int,default=4)
    args=parser.parse_args(); config=read_json(args.config); output=args.output.resolve()
    if args.max_clips<1: raise ValueError('positive review limit required')
    output.mkdir(parents=True,exist_ok=False); progress=output/'status.json'
    try:
        if not torch.cuda.is_available(): raise ValueError('CUDA unavailable; no fallback')
        torch.set_num_threads(config['threads']); torch.cuda.set_per_process_memory_fraction(config['gpu_memory_fraction'])
        dataset=ROOT/config['data_directory']/'dataset.json'; store=CorpusStore(dataset,'validation')
        payload,pointer=snapshot(ROOT/config['run_directory'],output,args.snapshot,contract(config,dataset,'cuda'))
        network=TemporalProposal(3072,config['hidden_size']).cuda(); network.load_state_dict(payload['model'],strict=True); network.eval()
        chosen=review_selection(store.shards,args.max_clips); clips=[]
        for number,shard in enumerate(chosen,1):
            directory=output/f'validation-{number:02d}-{shard["clip_id"][:12]}'; directory.mkdir()
            source=(dataset.parent/shard['payload']).parent; view_path=source/'images.json'
            if digest(view_path)!=shard['image_view_sha256']: raise ValueError('image view changed')
            view=read_json(view_path); validate_image_view(view,config['context_frames']); ports=corpus_ports(view['settings'])
            if (ports!=shard['slot_ports'] or view['replay_sha256']!=shard['replay_sha256']
                    or digest(Path(__file__).with_name('train_smoke.py'))!=shard['preprocessing_sha256']
                    or digest(Path(torch.hub.get_dir())/'checkpoints/resnet18-f37072fd.pth')!=shard['encoder_weights_sha256']):
                raise ValueError('review preprocessing, identity or slot mapping differs')
            status(progress,'predicting',clip=number,total=len(chosen),checkpoint_step=payload['step'])
            features=encode_images(view_path,view,32,torch.device('cuda'))
            half=config['context_frames']//2; centers=list(range(half,len(features)-half)); rows=[]
            characters=[p['character'] for p in sorted(view['settings']['players'],key=lambda p:p['port'])]
            with torch.no_grad():
                for start in range(0,len(centers),config['batch_size']):
                    indices=centers[start:start+config['batch_size']]
                    windows=torch.stack([features[i-half:i+half+1] for i in indices]).cuda()
                    predictions={k:v.cpu() for k,v in network(windows).items()}
                    rows.extend(decode_batch(predictions,[view['frames'][i] for i in indices],ports,characters))
            prediction={'schema':1,'kind':'frozen-image-controller-predictions','replay_sha256':view['replay_sha256'],
                'view_sha256':digest(view_path),'checkpoint_sha256':pointer['sha256'],'checkpoint_step':payload['step'],
                'training_regression':False,'settings':view['settings'],'slot_ports':ports,'slot_characters':characters,
                'slot_mapping':'ascending-physical-ports','prediction_interval':[rows[0]['frame'],rows[-1]['frame']],
                'context_frames':config['context_frames'],'rows':rows,
                'native_vi_adapter_verified':False,'generated_replay_validated':False}
            predictions_path=directory/'predictions.json'; atomic_json(predictions_path,prediction)
            constrained = button_decoder.constrain_buttons(prediction)
            constrained['button_decoder'].update(source_predictions_sha256=digest(predictions_path),
                decoder_sha256=digest(Path(button_decoder.__file__)))
            constrained_path=directory/'constrained-predictions.json'; atomic_json(constrained_path,constrained)
            # Both raw and constrained predictions are frozen before locating
            # or opening scoring answers. No decoding choices are fitted here.
            labels_path=ROOT/shard['labels']
            if digest(labels_path)!=shard['labels_sha256']: raise ValueError('scoring labels changed')
            labels=read_json(labels_path); score=score_predictions(prediction,labels)
            atomic_json(directory/'score.json',score)
            constrained_score=score_predictions(constrained,labels)
            atomic_json(directory/'constrained-score.json',constrained_score)
            comparison={'schema':1,'kind':'raw-constrained-button-comparison','checkpoint_step':payload['step'],
                'raw_predictions_sha256':digest(predictions_path),'constrained_predictions_sha256':digest(constrained_path),
                'labels_sha256':digest(labels_path),'player_frames':len(rows),
                'raw':{'button_metrics':score['button_metrics'],'consistency':button_decoder.button_consistency(prediction)},
                'constrained':{'button_metrics':constrained_score['button_metrics'],
                    'consistency':button_decoder.button_consistency(constrained)},
                'changed_button_frames':constrained['button_decoder']['changed_button_frames'],
                'policy':'equal fixed head weights; no label fitting; axes/action/airborne unchanged; no training update'}
            atomic_json(directory/'comparison.json',comparison)
            status(progress,'rendering',clip=number,total=len(chosen),checkpoint_step=payload['step'])
            subprocess.run([sys.executable,'scripts/render_prediction_review.py','--view',str(view_path),
                '--predictions',str(constrained_path),'--raw-predictions',str(predictions_path),
                '--labels',str(labels_path),'--output',str(directory/'video')],cwd=ROOT,check=True)
            mkv=directory/'video/prediction-review.mkv'; mp4=directory/'prediction-review.mp4'
            subprocess.run(['ffmpeg','-v','error','-n','-i',str(mkv),'-c:v','libx264','-crf','18','-preset','fast',
                '-pix_fmt','yuv420p','-movflags','+faststart',str(mp4)],check=True)
            clips.append({'clip_id':shard['clip_id'],'mp4':str(mp4.relative_to(output)),'mp4_sha256':digest(mp4),
                'mkv':str(mkv.relative_to(output)),'frames':len(view['frames']),
                'button_metrics':constrained_score['button_metrics'],'raw_button_metrics':score['button_metrics'],
                'comparison':comparison})
            print(f"Clip {number}/{len(chosen)}: raw invalid button-frames "
                f"{comparison['raw']['consistency']['invalid_button_frames']}; constrained "
                f"{comparison['constrained']['consistency']['invalid_button_frames']}",flush=True)
        aggregate=aggregate_comparisons(clips); atomic_json(output/'comparison.json',aggregate)
        atomic_json(output/'review.json',{'schema':1,'kind':'corpus-model-controller-review','checkpoint':pointer,
            'clips':clips,'available_validation_clips':len(store.shards),'selection':'fixed sorted round-robin across rosters; no score-based selection',
            'button_decoder':button_decoder.METHOD,'decoder_sha256':digest(Path(button_decoder.__file__)),
            'comparison':aggregate,'test_matches_opened':0,'generated_gameplay':False,'training_updated':False})
        status(progress,'complete',checkpoint_step=payload['step'],clips=clips)
    except BaseException as error:
        status(progress,'failed',error=str(error)); raise


if __name__=='__main__': main()
