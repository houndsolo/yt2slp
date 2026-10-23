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
    args = parser.parse_args()
    view, predictions, labels = (json.loads(p.read_text()) for p in (args.view, args.predictions, args.labels))
    if predictions['view_sha256'] != sha256(args.view): raise ValueError('review view differs from inference')
    score_predictions(predictions, labels)  # Same exact-key/mask/identity guard as scoring.
    args.output.mkdir(parents=True, exist_ok=False)
    predicted = {(r['frame'], r['port']): r for r in predictions['rows']}
    recorded = {(r['frame'], r['port']): r for r in labels['rows']}
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 14)
    def buttons(value, valid=True):
        return ' '.join(name.upper() for name, bit in BUTTONS.items() if value & bit) or '-' if valid else '?'
    frames = args.output/'frames'; frames.mkdir()
    for frame in view['frames']:
        source = args.view.parent/frame['image']
        if sha256(source) != frame['image_sha256']: raise ValueError('review source image changed')
        with Image.open(source) as original:
            canvas = Image.new('RGB', (original.width+600, original.height), '#111a26')
            canvas.paste(original, (0, 0)); x = original.width+14
        lines = ['CONTROLLER PREDICTION REVIEW', 'Left: original replay footage', 'Generated game/replay: pending',
            f"Signed frame {frame['replay_frame']} | 60 fps", '']
        for player in sorted(view['settings']['players'], key=lambda p:p['port']):
            key = (frame['replay_frame'], player['port']); actual = recorded[key]; guess = predicted.get(key)
            character = {2:'Fox',20:'Falco'}.get(player['character'], str(player['character']))
            lines += [f"P{player['port']+1} {character}   RECORDED / MODEL"]
            for head, actual_bits, valid in (
                ('hold', actual['physical']['values']['buttons'], actual['physical']['mask']['buttons']),
                ('press', actual['physical_edges']['pressed'], actual['physical_edges']['mask']),
                ('release', actual['physical_edges']['released'], actual['physical_edges']['mask'])):
                value = buttons(guess['buttons'][head]) if guess else 'context only'
                lines += [f'{head:7} {buttons(actual_bits, valid):14} / {value}']
            for axis in AXES:
                a = f"{actual['effective']['values'][axis]:+.3f}" if actual['effective']['mask'][axis] else '?'
                b = f"{guess['axes'][axis]:+.3f}" if guess else '--'
                lines += [f'{axis:9} {a:14} / {b}']
            lines += ['']
        lines += ['Scores are uncalibrated; edges independent.', 'First/last 15 frames supply temporal context.']
        ImageDraw.Draw(canvas).multiline_text((x, 12), '\n'.join(lines), font=font, fill='#e2ecf5', spacing=2)
        canvas.save(frames/f"{frame['index']:06d}.png")
    movie = args.output/'prediction-review.mkv'
    subprocess.run(['ffmpeg','-v','error','-n','-framerate','60','-i',str(frames/'%06d.png'),
        '-c:v','ffv1','-level','3','-pix_fmt','yuv420p',str(movie)], check=True)
    result = {'schema':1,'kind':'controller-prediction-review','video_sha256':sha256(movie),
        'view_sha256':sha256(args.view),'predictions_sha256':sha256(args.predictions),'labels_sha256':sha256(args.labels),
        'frames':len(view['frames']),'fps':60,'generated_gameplay':False,
        'policy':'source footage plus post-prediction recorded/model controller panels; no synthetic gameplay or replay'}
    (args.output/'review.json').write_text(json.dumps(result, indent=2)+'\n')
    print(movie)


if __name__ == '__main__': main()
