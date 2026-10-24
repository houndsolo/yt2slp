"""Verify an actual official Playback capture of a known-input roundtrip.

Effective pre-frame controls and nine post fields are separate strict gates.
Physical PAD fields are diagnostic; no frame offset or tolerance is fitted.
"""
import argparse
import json
from pathlib import Path
import subprocess

from yt2slp.benchmark import compare_posts
from yt2slp.pad_adapter import compare_control_labels
from yt2slp.video import sha256


def node(tool,*arguments):
    return json.loads(subprocess.check_output(['node','tools/slippi-parser/'+tool,*map(str,arguments)]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('calibration','capture','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--case',choices=('clock','clock-preroll','hop-1','hop-2','hop-3'),required=True)
    args=parser.parse_args()
    result=json.loads((args.calibration/'result.json').read_text())
    capture=json.loads((args.capture/'capture.json').read_text())
    reference=args.calibration/args.case/'native.slp';roundtrip=args.calibration/f'roundtrip-{args.case}.slp'
    if (not result['passed'] or sha256(args.calibration/'profile.json')!=result['profile_sha256']
            or sha256(reference)!=sha256(roundtrip) or capture.get('capture_passed') is not True
            or capture.get('playback_version')!='3.5.2' or capture.get('should_resync') is not False
            or capture['source_replay_sha256']!=sha256(roundtrip) or capture['request_interval'][0]!=-123
            or len(capture['regenerated_replays'])!=1):
        raise ValueError('successful bound calibration, exact roundtrip and actual official capture required')
    first,last=capture['wanted_interval']; candidate=args.capture/capture['regenerated_replays'][0]
    posts=compare_posts(node('export-state.cjs',reference),node('export-state.cjs',candidate),first,last)
    controls=compare_control_labels(node('export-training.cjs',reference,first,last),
        node('export-training.cjs',candidate,first,last),first,last)
    report={'schema':1,'kind':'native-pad-official-verification','case':args.case,
        'passed':posts['passed'] and controls['passed'],'interval':[first,last],
        'source_vs_roundtrip_bytes_match':True,'actual_playback_progression':True,
        'post_state':posts,'controls':controls,'full_state_equality_established':False,
        'source_ucf_parity_established':False,'learned_reconstruction':False,
        'identities':{str(p):sha256(p) for p in (reference,roundtrip,candidate,args.capture/'capture.json',
            args.calibration/'profile.json',Path(__file__),Path('src/yt2slp/pad_adapter.py'))}}
    with args.output.open('x') as handle:handle.write(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'case':args.case,'interval':[first,last],
        'effective_controls':controls['groups']['effective']['passed'],'physical_diagnostics':controls['groups']['physical']['passed'],
        'post_state':posts['passed']},indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
