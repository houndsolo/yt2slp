"""Project prepared source video into an image-only view with known roster."""
import argparse
from pathlib import Path
from yt2slp.model_contract import image_view

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--video', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
result = image_view(args.video, args.output)
print(f"{len(result['frames'])} images; no controller/state target file opened")
