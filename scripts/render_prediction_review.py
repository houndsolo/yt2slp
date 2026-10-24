"""Render source footage beside recorded/predicted controls, not a game reconstruction.

Requires the optional learning environment's Pillow and the development FFmpeg.
"""
import argparse
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont
from yt2slp.prediction_scoring import BUTTONS, AXES, score_predictions
from yt2slp.video import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('view', 'predictions', 'labels', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--raw-predictions', type=Path, help='show recorded/raw/constrained control columns')
    args = parser.parse_args()
    view, predictions, labels = (json.loads(p.read_text()) for p in (args.view, args.predictions, args.labels))
    if predictions['view_sha256'] != sha256(args.view): raise ValueError('review view differs from inference')
    score_predictions(predictions, labels)  # Same exact-key/mask/identity guard as scoring.
    raw = None
    if args.raw_predictions:
        raw = json.loads(args.raw_predictions.read_text()); score_predictions(raw, labels)
        if (raw['view_sha256'] != predictions['view_sha256']
                or raw['checkpoint_sha256'] != predictions['checkpoint_sha256']
                or raw['prediction_interval'] != predictions['prediction_interval']
                or predictions.get('button_decoder', {}).get('source_predictions_sha256') != sha256(args.raw_predictions)):
            raise ValueError('raw/constrained comparison identity mismatch')
    args.output.mkdir(parents=True, exist_ok=False)
    predicted = {(r['frame'], r['port']): r for r in predictions['rows']}
    raw_rows = {(r['frame'], r['port']): r for r in raw['rows']} if raw else {}
    if raw and any({k: v for k, v in row.items() if k != 'buttons'} !=
                   {k: v for k, v in raw_rows[key].items() if k != 'buttons'} for key, row in predicted.items()):
        raise ValueError('button decoding changed non-button predictions')
    recorded = {(r['frame'], r['port']): r for r in labels['rows']}
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 14)
    def buttons(value, valid=True):
        return ' '.join(name.upper() for name, bit in BUTTONS.items() if value & bit) or '-' if valid else '?'
    def compact(value, valid=True):
        if not valid: return '?'
        return ' '.join(symbol if value & bit else '.' for symbol, bit in
            zip(('<', '>', 'v', '^', 'Z', 'R', 'L', 'A', 'B', 'X', 'Y', 'S'), BUTTONS.values()))
    frames = args.output/'frames'; frames.mkdir()
    for frame in view['frames']:
        source = args.view.parent/frame['image']
        if sha256(source) != frame['image_sha256']: raise ValueError('review source image changed')
        with Image.open(source) as original:
            canvas = Image.new('RGB', (original.width+(900 if raw else 600), original.height), '#111a26')
            canvas.paste(original, (0, 0)); x = original.width+14
        lines = ['CONTROLLER PREDICTION REVIEW', 'Left: original replay footage', 'Generated game/replay: pending',
            f"Signed frame {frame['replay_frame']} | 60 fps", '']
        for player in sorted(view['settings']['players'], key=lambda p:p['port']):
            key = (frame['replay_frame'], player['port']); actual = recorded[key]; guess = predicted.get(key)
            raw_guess = raw_rows.get(key)
            character = {2:'Fox',20:'Falco'}.get(player['character'], str(player['character']))
            lines += [f"P{player['port']+1} {character}   "+('RECORDED / RAW MODEL / CONSTRAINED' if raw else 'RECORDED / MODEL')]
            for head, actual_bits, valid in (
                ('hold', actual['physical']['values']['buttons'], actual['physical']['mask']['buttons']),
                ('press', actual['physical_edges']['pressed'], actual['physical_edges']['mask']),
                ('release', actual['physical_edges']['released'], actual['physical_edges']['mask'])):
                if raw:
                    original = compact(actual_bits, valid)
                    independent = compact(raw_guess['buttons'][head]) if raw_guess else 'context only'
                    constrained = compact(guess['buttons'][head]) if guess else 'context only'
                    lines += [f'{head:7} {original:23} | {independent:23} | {constrained}']
                else:
                    value = buttons(guess['buttons'][head]) if guess else 'context only'
                    lines += [f'{head:7} {buttons(actual_bits, valid):14} / {value}']
            for axis in AXES:
                a = f"{actual['effective']['values'][axis]:+.3f}" if actual['effective']['mask'][axis] else '?'
                b = f"{guess['axes'][axis]:+.3f}" if guess else '--'
                lines += [f'{axis:9} {a:14} / {b}'+(' (raw = constrained)' if raw else '')]
            lines += ['']
        method = predictions.get('button_decoder', {}).get('method')
        seed = method == 'held-state-difference-v1'
        lines += [('Buttons: < > v ^ Z R L A B X Y S; dot = released.' if raw else 'Model scores are uncalibrated.'),
            ('Edges derived from consecutive held states.' if seed else
             'Viterbi: valid button transitions; scores uncalibrated.' if method else 'Hold/press/release heads are independent.')]
        if seed: lines += ['Trigger: digital L/R = 1; Z overrides to 0.35.']
        half = predictions.get('context_frames', 31)//2
        lines += [f"Context: first {predictions.get('leading_context_frames', half)}, last {predictions.get('trailing_context_frames', half)} frames."]
        ImageDraw.Draw(canvas).multiline_text((x, 12), '\n'.join(lines), font=font, fill='#e2ecf5', spacing=2)
        canvas.save(frames/f"{frame['index']:06d}.png")
    movie = args.output/'prediction-review.mkv'
    subprocess.run(['ffmpeg','-v','error','-n','-framerate','60','-i',str(frames/'%06d.png'),
        '-c:v','ffv1','-level','3','-pix_fmt','yuv420p',str(movie)], check=True)
    result = {'schema':1,'kind':'controller-prediction-review','video_sha256':sha256(movie),
        'view_sha256':sha256(args.view),'predictions_sha256':sha256(args.predictions),'labels_sha256':sha256(args.labels),
        'frames':len(view['frames']),'fps':60,'generated_gameplay':False,
        'raw_predictions_sha256':sha256(args.raw_predictions) if raw else None,
        'button_decoding':predictions.get('button_decoder', {}).get('method', 'independent-zero-logit'),
        'policy':'source footage plus post-prediction recorded/model controller panels; no synthetic gameplay or replay'}
    (args.output/'review.json').write_text(json.dumps(result, indent=2)+'\n')
    print(movie)


if __name__ == '__main__': main()
