"""Bind a trained checkpoint and its known player-slot contract before evaluation."""
import argparse
from pathlib import Path
from yt2slp.model_contract import freeze_model

parser = argparse.ArgumentParser(description=__doc__)
for name in ('pairs', 'checkpoint', 'output'): parser.add_argument('--'+name, type=Path, required=True)
args = parser.parse_args()
result = freeze_model(args.pairs, args.checkpoint, args.output)
print(f"Frozen checkpoint {result['checkpoint_sha256']}; slots {result['slot_characters']}")
