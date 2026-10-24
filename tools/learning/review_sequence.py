"""Image-only saved-model review with derived edges and shoulder/Z constraints."""
import argparse
from pathlib import Path
import subprocess
import sys

from train_smoke import torch, encode_images
from corpus_data import CorpusStore
from review_corpus import review_selection
from review_run import snapshot
from runtime_files import ROOT, atomic_json, digest, read_json, status
from sequence_model import SequenceProposal, proposal_rows
from train_sequence import contract, infer_clip
from yt2slp import sequence_controls
from yt2slp.corpus import corpus_ports
from yt2slp.model_contract import validate_image_view
from yt2slp.prediction_scoring import score_predictions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--snapshot', choices=('latest', 'best'), default='latest')
    parser.add_argument('--max-clips', type=int, default=4)
    args = parser.parse_args(); config = read_json(args.config); output = args.output.resolve()
    if not 1 <= args.max_clips <= 55: raise ValueError('bounded positive review count required')
    output.mkdir(parents=True, exist_ok=False); progress = output/'status.json'
    try:
        if not torch.cuda.is_available(): raise ValueError('CUDA unavailable; no fallback')
        torch.set_num_threads(config['threads']); torch.cuda.set_per_process_memory_fraction(config['gpu_memory_fraction'])
        dataset = ROOT/config['data_directory']/'dataset.json'; store = CorpusStore(dataset, 'validation')
        payload, pointer = snapshot(ROOT/config['run_directory'], output, args.snapshot, contract(config, dataset, 'cuda'))
        network = SequenceProposal(3072, config['hidden_size']).cuda(); network.load_state_dict(payload['model'], strict=True); network.eval()
        chosen = review_selection(store.shards, args.max_clips); clips = []
        for number, shard in enumerate(chosen, 1):
            directory = output/f'validation-{number:02d}-{shard["clip_id"][:12]}'; directory.mkdir()
            view_path = (dataset.parent/shard['payload']).parent/'images.json'
            if digest(view_path) != shard['image_view_sha256']: raise ValueError('image view changed')
            view = read_json(view_path); validate_image_view(view, config['context_frames']); ports = corpus_ports(view['settings'])
            if (ports != shard['slot_ports'] or view['replay_sha256'] != shard['replay_sha256']
                    or digest(Path(__file__).with_name('train_smoke.py')) != shard['preprocessing_sha256']
                    or digest(Path(torch.hub.get_dir())/'checkpoints/resnet18-f37072fd.pth') != shard['encoder_weights_sha256']):
                raise ValueError('review preprocessing, identity or slot mapping differs')
            status(progress, 'predicting', clip=number, total=len(chosen), checkpoint_step=payload['step'])
            features = encode_images(view_path, view, 32, torch.device('cuda')); half = config['context_frames']//2
            prediction = infer_clip(network, features, config['context_frames'], torch.device('cuda'), 64)
            characters = [p['character'] for p in sorted(view['settings']['players'], key=lambda p: p['port'])]
            rows = proposal_rows(prediction, view['frames'][half:len(features)-half], ports, characters)
            proposals = {'schema': 1, 'kind': 'frozen-image-held-state-proposals',
                'replay_sha256': view['replay_sha256'], 'view_sha256': digest(view_path),
                'checkpoint_sha256': pointer['sha256'], 'checkpoint_step': payload['step'],
                'training_regression': False, 'settings': view['settings'], 'slot_ports': ports,
                'slot_characters': characters, 'slot_mapping': 'ascending-physical-ports',
                'prediction_interval': [rows[0]['frame'], rows[-1]['frame']], 'rows': rows,
                'context_frames': config['context_frames'], 'native_vi_adapter_verified': False, 'generated_replay_validated': False}
            proposals_path = directory/'held-state-proposals.json'; atomic_json(proposals_path, proposals)
            decoded = sequence_controls.decode_sequence(proposals)
            decoded['button_decoder'].update(source_proposals_sha256=digest(proposals_path),
                decoder_sha256=digest(Path(sequence_controls.__file__)))
            predictions_path = directory/'predictions.json'; atomic_json(predictions_path, decoded)
            # Locate/read original scoring answers only after image-only output
            # and both the button and trigger rules have been frozen.
            labels_path = ROOT/shard['labels']
            if digest(labels_path) != shard['labels_sha256']: raise ValueError('scoring labels changed')
            score = score_predictions(decoded, read_json(labels_path)); atomic_json(directory/'score.json', score)
            status(progress, 'rendering', clip=number, total=len(chosen), checkpoint_step=payload['step'])
            subprocess.run([sys.executable, 'scripts/render_prediction_review.py', '--view', str(view_path),
                '--predictions', str(predictions_path), '--labels', str(labels_path), '--output', str(directory/'video')], cwd=ROOT, check=True)
            mkv = directory/'video/prediction-review.mkv'; mp4 = directory/'prediction-review.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-n', '-i', str(mkv), '-c:v', 'libx264', '-crf', '18',
                '-preset', 'fast', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(mp4)], check=True)
            clips.append({'clip_id': shard['clip_id'], 'mp4': str(mp4.relative_to(output)), 'mp4_sha256': digest(mp4),
                'mkv': str(mkv.relative_to(output)), 'frames': len(view['frames']), 'button_metrics': score['button_metrics'],
                'constraint_metrics': decoded['button_decoder']['consistency'], 'trigger_constraint': decoded['trigger_constraint']})
        atomic_json(output/'review.json', {'schema': 1, 'kind': 'sequence-model-controller-review', 'checkpoint': pointer,
            'clips': clips, 'selection': 'fixed sorted roster round-robin; no score selection',
            'test_matches_opened': 0, 'generated_gameplay': False, 'training_updated': False})
        status(progress, 'complete', checkpoint_step=payload['step'], clips=clips)
    except BaseException as error:
        status(progress, 'failed', error=str(error)); raise


if __name__ == '__main__': main()
