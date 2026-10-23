"""Freeze known-roster match/date splits using settings only, before rendering."""
import argparse
import hashlib
import json
from pathlib import Path
from yt2slp.learning_data import validate_split_plan


def plan_matches(entries, reserved):
    reservations = validate_split_plan(reserved)
    reserved_groups = {r['group']: r['split'] for r in reservations.values()}
    matches = []
    for row in entries:
        if (row['status'] != 'eligible_singles_settings' or row['stage'] != 31
                or sorted(p['character'] for p in row['players']) != [2,20]
                or not row.get('capture_date_from_filename') or (row.get('last_frame') or 0) < 602):
            continue
        digest = row['replay_sha256']
        date = row['capture_date_from_filename']; group = 'capture-date-'+date
        bucket = int(hashlib.sha256(('yt2slp-vision-split-v1:'+group).encode()).hexdigest()[:8],16)%100
        split = reserved_groups.get(group, 'test' if bucket < 15 else 'validation' if bucket < 30 else 'train')
        original = reservations.get(digest)
        if original and original['split'] != split: raise ValueError('reserved split changed')
        matches.append({'file':'recordings/examples/'+row['file'], 'replay_sha256':digest,
            'group':group, 'split':split, 'previously_examined':bool(original), 'stage':31,
            'players':row['players'], 'last_frame':row['last_frame']})
    result = {'schema':1,'scope':'Fox/Falco Battlefield; frozen content/date groups before labels/windows',
        'grouping':'filename dates; player disjointness unverified; original pilot reservations retained',
        'assignment':'SHA256(yt2slp-vision-split-v1:group) first 32 bits modulo 100; <15 test, <30 validation, otherwise train; reserved dates override',
        'matches':sorted(matches,key=lambda r:r['file'])}
    validate_split_plan(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('entries','reserved','output'): parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    result = plan_matches([json.loads(s) for s in args.entries.read_text().splitlines()],json.loads(args.reserved.read_text()))
    with args.output.open('x') as handle: handle.write(json.dumps(result,indent=2)+'\n')
    print({s:sum(m['split']==s for m in result['matches']) for s in ('train','validation','test')})


if __name__ == '__main__': main()
