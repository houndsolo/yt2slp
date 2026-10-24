"""Constrain saved image predictions without loading labels or a model."""
import argparse
import json
from pathlib import Path

from yt2slp import button_decoder
from yt2slp.video import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = button_decoder.constrain_buttons(json.loads(args.predictions.read_text()))
    result['button_decoder'].update(source_predictions_sha256=sha256(args.predictions),
        decoder_sha256=sha256(Path(button_decoder.__file__)))
    with args.output.open('x') as handle:
        handle.write(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(result['button_decoder'], indent=2))


if __name__ == '__main__': main()
