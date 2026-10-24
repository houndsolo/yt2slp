"""Review a paired vision checkpoint on fixed development images, not controls."""
import argparse
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont, ImageOps
from train_smoke import torch
from review_corpus import review_selection
from review_run import snapshot
from runtime_files import ROOT, atomic_json, digest, read_json, status
from state_data import StateStore
from state_model import make_models, normalize, state_counts, summarize_counts
from train_state import contract


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--snapshot', choices=('latest', 'best'), default='latest')
    args = parser.parse_args(); config = read_json(args.config); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    progress = output/'status.json'
    try:
        if not torch.cuda.is_available(): raise ValueError('CUDA unavailable; no fallback')
        torch.set_num_threads(config['threads']); torch.cuda.set_per_process_memory_fraction(config['gpu_memory_fraction'])
        dataset = ROOT/config['data_directory']/'dataset.json'; store = StateStore(dataset, 'validation')
        payload, pointer = snapshot(ROOT/config['run_directory'], output, args.snapshot, contract(config, dataset, 'cuda'))
        prefix, models = make_models(ROOT/config['encoder_weights']); prefix = prefix.cuda().eval()
        for name, model in models.items(): model.load_state_dict(payload['models'][name], strict=True); model.cuda().eval()
        clips = []; font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 16)
        for number, shard in enumerate(review_selection(store.shards, 2), 1):
            index = next(i for i, s in enumerate(store.shards) if s['clip_id'] == shard['clip_id'])
            directory = output/f'validation-{number:02d}-{shard["clip_id"][:12]}'; directory.mkdir()
            inputs = store.load(index, 'inputs'); view_path = dataset.parent/shard['view']; view = read_json(view_path)
            status(progress, 'predicting', clip=number, total=2, checkpoint_step=payload['step']); predicted = {name: {} for name in models}
            with torch.no_grad():
                for start in range(0, shard['frames'], config['batch_size']):
                    features = prefix(normalize(inputs['images'][start:start+config['batch_size']], 'cuda'))
                    setup = inputs['setup'][start:start+config['batch_size']].cuda()
                    for name, model in models.items():
                        for key, values in model(features, setup).items(): predicted[name].setdefault(key, []).append(values.cpu())
            predictions = {name: {k: torch.cat(v) for k, v in values.items()} for name, values in predicted.items()}
            frozen = directory/'image-state-predictions.pt'; torch.save(predictions, frozen)
            atomic_json(directory/'predictions.json', {'kind': 'paired-image-state-predictions', 'checkpoint': pointer,
                'payload_sha256': digest(frozen), 'view_sha256': digest(view_path), 'inputs_sha256': shard['inputs_sha256'],
                'ports': shard['slot_ports'], 'signed_frames': [f['replay_frame'] for f in view['frames']],
                'supplied_setup': view['settings'], 'labels_loaded': False, 'controller_outputs': False})
            # Both branches' image-only outputs are now frozen; open state answers.
            targets = store.load(index, 'targets'); scores = {name: summarize_counts(state_counts(value, targets)) for name, value in predictions.items()}
            atomic_json(directory/'score.json', scores); frames = directory/'frames'; frames.mkdir()
            status(progress, 'rendering', clip=number, total=2, checkpoint_step=payload['step'])
            for frame_index, frame in enumerate(view['frames']):
                source = view_path.parent/frame['image']
                if digest(source) != frame['image_sha256']: raise ValueError('review source PNG changed')
                with Image.open(source) as source_image:
                    original = source_image.convert('RGB'); canvas = Image.new('RGB', (original.width+600, original.height), '#111a26')
                    canvas.paste(original, (0, 0)); x = original.width+14; draw = ImageDraw.Draw(canvas)
                    draw.multiline_text((x, 12), 'VISION STATE REVIEW\nOriginal footage; frozen / fine-tuned CNN\n'
                        f"Signed frame {frame['replay_frame']}; sampled {60/config['frame_stride']:g} fps", font=font, fill='white', spacing=3)
                    for slot, player in enumerate(sorted(view['settings']['players'], key=lambda p: p['port'])):
                        y = 88+slot*195
                        action = str(int(targets['action'][frame_index, slot])) if targets['action_mask'][frame_index, slot] else '?'
                        airborne = str(bool(targets['airborne'][frame_index, slot])) if targets['airborne_mask'][frame_index, slot] else '?'
                        f, t = predictions['frozen'], predictions['finetuned']
                        lines = [f"P{player['port']+1} char {player['character']} costume {player['costume']}",
                            '             recorded / frozen / tuned',
                            f"action       {action} / {int(f['action'][frame_index,slot].argmax())} / {int(t['action'][frame_index,slot].argmax())}",
                            f"airborne     {airborne} / {bool(f['airborne'][frame_index,slot]>=0)} / {bool(t['airborne'][frame_index,slot]>=0)}"]
                        draw.multiline_text((x, y), '\n'.join(lines), font=font, fill='#e2ecf5', spacing=3)
                        for column, name in enumerate(('frozen', 'finetuned')):
                            attention = predictions[name]['attention'][frame_index, slot]; attention = attention/attention.max().clamp_min(1e-12)
                            grey = Image.frombytes('L', (attention.shape[1], attention.shape[0]), bytes((attention*255).byte().flatten().tolist()))
                            heat = Image.merge('RGB', (grey, Image.new('L', grey.size), Image.new('L', grey.size))).resize((128, 96), Image.Resampling.BILINEAR)
                            thumb = ImageOps.pad(original, (384, 320), method=Image.Resampling.BILINEAR).resize((128, 96), Image.Resampling.BILINEAR)
                            canvas.paste(Image.blend(thumb, heat, .45), (x+column*170, y+80))
                    draw.text((x, original.height-28), 'Attention is diagnostic; no tracked boxes.', font=font, fill='#e2ecf5')
                    canvas.save(frames/f'{frame_index:06d}.png')
            mkv = directory/'state-review.mkv'; mp4 = directory/'state-review.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-n', '-framerate', f"60/{config['frame_stride']}", '-i', str(frames/'%06d.png'),
                '-c:v', 'ffv1', '-level', '3', '-pix_fmt', 'yuv420p', str(mkv)], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-n', '-i', str(mkv), '-c:v', 'libx264', '-crf', '18', '-preset', 'fast',
                '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(mp4)], check=True)
            clips.append({'clip_id': shard['clip_id'], 'mp4': str(mp4.relative_to(output)), 'mp4_sha256': digest(mp4),
                'frames': shard['frames'], 'fps': 60/config['frame_stride'], 'metrics': scores})
        atomic_json(output/'review.json', {'kind': 'matched-state-vision-review', 'checkpoint': pointer, 'clips': clips,
            'test_matches_opened': 0, 'controller_outputs': False, 'generated_gameplay': False, 'training_updated': False})
        status(progress, 'complete', checkpoint_step=payload['step'], clips=clips)
    except BaseException as error:
        status(progress, 'failed', error=str(error)); raise


if __name__ == '__main__': main()
