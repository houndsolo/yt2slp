"""Encode/ingest a validated controlled reference; keep its oracle outside video.json.

Run in Docker. Source controllers and posts remain source-generation/evaluation
artifacts. Reconstruction reads only the ingested MP4 and its visual annotations.
"""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import subprocess

from yt2slp.reference_cases import REFERENCE_CASES, validate_reference_report
from yt2slp.video import ingest_video, sha256


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--analysis',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run=args.run.resolve()
    analysis=args.analysis.resolve() if args.analysis else run/'analysis'
    report=json.loads((analysis/'result.json').read_text())
    replay,clip=run/'native.slp',analysis/'reference.mkv'
    validate_reference_report(report,sha256(replay),sha256(clip))
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    encoded=output/'source.mp4'
    command=['ffmpeg','-v','error','-i',str(clip),'-c:v','libx264','-crf','18','-preset','medium',
             '-pix_fmt','yuv420p',str(encoded)]
    try:
        parser_report=output/'source-parser.json'
        last=REFERENCE_CASES[report['case']].total_steps+1
        with parser_report.open('x') as handle:
            subprocess.run(['node','tools/slippi-parser/validate.cjs',str(replay),'--last-frame',str(last)],
                           stdout=handle,check=True)
        parsed=json.loads(parser_report.read_text())
        if parsed['replaySha256']!=sha256(replay) or parsed['gameEnd'] is not None:
            raise ValueError('source parser identity or declared partial-ending policy differs')
        subprocess.run(command,check=True,timeout=120)
        video=ingest_video(encoded,output/'ingested')
        if len(video['frames'])!=61 or any(Fraction(row['relative_seconds'])!=Fraction(i,60) for i,row in enumerate(video['frames'])):
            raise ValueError('transcode changed the declared reference count/timing')
        provenance={'schema':1,'kind':'controlled-source-video','case':report['case'],
            'source_replay_sha256':sha256(replay),'source_clip_sha256':sha256(clip),
            'video_sha256':video['source_sha256'],'command':command,'independent_parser_validated':True,
            'identities':{str(p):sha256(p) for p in (Path(__file__),Path('src/yt2slp/reference_cases.py'),
                Path('src/yt2slp/video.py'),analysis/'result.json',analysis/'native-state.json',
                output/'ingested/video.json',parser_report,Path('tools/slippi-parser/validate.cjs'),
                Path('tools/slippi-parser/package-lock.json'))},
            'policy':'controllers and source posts are not included in ingested video.json; optional oracle is evaluated only after selection'}
        (output/'source-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    except Exception as exc:
        (output/'preparation-failure.json').write_text(json.dumps({'error':str(exc)},indent=2)+'\n')
        raise
    print(output/'ingested/video.json')


if __name__=='__main__':
    main()
