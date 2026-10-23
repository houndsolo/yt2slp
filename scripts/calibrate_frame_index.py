"""Calibrate exact emulator UI glyphs from independently reviewed screenshots."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from yt2slp.frame_index import ALPHABET, GEOMETRY, add_calibration, cyan_cells, decode_index
from yt2slp.video import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--annotations', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error('new calibration path required')
    annotations = json.loads(args.annotations.read_text())
    templates = {}; sources = []; observed = []
    g = GEOMETRY; width = g['cells']*g['cell_width']; height = g['height']
    for anchor in annotations['anchors']:
        path = (args.annotations.parent/anchor['image']).resolve()
        if type(anchor['frame']) is not int or not anchor.get('note', '').strip():
            raise ValueError('integer index and explicit visual review note required')
        raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-frames:v', '1',
            '-vf', f'crop={width}:{height}:{g["left"]}:{g["top"]},format=rgb24', '-f', 'rawvideo', 'pipe:1'])
        cells = cyan_cells(raw, width, height, cropped=True)
        add_calibration(templates, cells, anchor['frame'])
        sources.append({**anchor, 'image': os.path.relpath(path, args.output.parent.resolve()), 'sha256': sha256(path)})
        observed.append((cells, anchor['frame']))
    if set(templates) != ALPHABET: raise ValueError('frame-index calibration lacks a required digit/symbol')
    result = {'schema': 1, 'geometry': dict(GEOMETRY), 'templates': templates, 'sources': sources,
        'annotations_sha256': sha256(args.annotations),
        'policy': 'independent literal visual readings of emulator UI; exact glyph equality only; no inferred log/display offset'}
    for cells, frame in observed:
        if decode_index(cells, result) != frame: raise ValueError('anchor does not reread exactly')
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(args.output)


if __name__ == '__main__': main()
