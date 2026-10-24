"""Freeze the larger known-stage corpus using settings only, before labels."""
import argparse
import json
from pathlib import Path

from yt2slp.corpus import plan_corpus
from yt2slp.video import sha256


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('entries','reserved','output'): parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    result=plan_corpus([json.loads(line) for line in args.entries.read_text().splitlines()],json.loads(args.reserved.read_text()))
    result['identities']={'catalog':sha256(args.entries),'previous_plan':sha256(args.reserved)}
    with args.output.open('x') as handle: handle.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({s:sum(m['split']==s for m in result['matches']) for s in ('train','validation','test')}))


if __name__=='__main__': main()
