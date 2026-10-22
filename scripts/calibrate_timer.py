"""Build a local timer-glyph calibration from manually verified captured labels."""
import argparse,json
from pathlib import Path
from yt2slp.timer_labels import calibrate
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--annotations',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
result=calibrate(json.loads(a.annotations.read_text()),a.annotations.parent)
with a.output.open('x') as handle:json.dump(result,handle,indent=2);handle.write('\n')
print(a.output)
