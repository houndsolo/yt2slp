"""Score a saved prediction artifact; this tool never loads a model."""
import argparse
import json
from pathlib import Path
from yt2slp.prediction_scoring import score_predictions
from yt2slp.video import sha256

parser = argparse.ArgumentParser(description=__doc__)
for name in ('predictions', 'labels', 'output'): parser.add_argument('--'+name, type=Path, required=True)
args = parser.parse_args()
result = score_predictions(json.loads(args.predictions.read_text()), json.loads(args.labels.read_text()))
result['predictions_sha256'] = sha256(args.predictions); result['labels_sha256'] = sha256(args.labels)
with args.output.open('x') as handle: handle.write(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
