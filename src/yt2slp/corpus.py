"""Settings-only Fox mirror/Fox–Falco corpus policy and explicit physical slots."""
import hashlib

from .learning_data import validate_split_plan


def corpus_ports(settings):
    players = sorted(settings['players'], key=lambda p:p['port'])
    if (settings.get('stage')!=31 or len(players)!=2
            or sorted(p['character'] for p in players) not in ([2,2],[2,20])
            or len({p['port'] for p in players})!=2
            or any(type(p['port']) is not int or not 0<=p['port']<=3 for p in players)
            or (players[0]['character']==players[1]['character'] and players[0]['costume']==players[1]['costume'])):
        raise ValueError('Battlefield Fox/Fox (distinct costumes) or Fox/Falco physical slots required')
    return [p['port'] for p in players]


def plan_corpus(entries, reserved, frames=1200, clips_per_match=3):
    previous = validate_split_plan(reserved)
    groups = {m['group']:m['split'] for m in previous.values()}
    if type(frames) is not int or not 31<=frames<=1800 or type(clips_per_match) is not int or not 1<=clips_per_match<=8:
        raise ValueError('bounded clip length and count required')
    matches = []; skipped = {}; seen = set()
    for row in entries:
        reason = None
        if row.get('status')!='eligible_singles_settings': reason='not_eligible_singles'
        elif row.get('stage')!=31: reason='other_stage'
        elif sorted(p['character'] for p in row['players']) not in ([2,2],[2,20]): reason='other_roster'
        elif row.get('is_pal') or row.get('timer_type')!=2 or row.get('timer_seconds')!=480 or any(p['type']!=0 or p['stocks']!=4 for p in row['players']): reason='rules'
        elif not row.get('capture_date_from_filename'): reason='unknown_date'
        else:
            try: corpus_ports(row)
            except ValueError: reason='ambiguous_mirror_or_ports'
        end = min(row.get('last_frame') or 0,28800)-120
        if reason is None and end-600 < frames*clips_per_match: reason='too_short'
        if reason:
            skipped[reason] = skipped.get(reason,0)+1; continue
        digest = row['replay_sha256']
        if digest in seen: raise ValueError('duplicate content in eligible catalog')
        seen.add(digest)
        group = 'capture-date-'+row['capture_date_from_filename']
        bucket = int(hashlib.sha256(('yt2slp-vision-split-v1:'+group).encode()).hexdigest()[:8],16)%100
        split = groups.get(group,'test' if bucket<15 else 'validation' if bucket<30 else 'train')
        if digest in previous and previous[digest]['split']!=split: raise ValueError('frozen source split changed')
        clips = []
        for number in range(clips_per_match):
            left = 601+(end-600)*number//clips_per_match
            right = 601+(end-600)*(number+1)//clips_per_match-1
            jitter = hashlib.sha256(f'yt2slp-corpus-v3:{digest}:{number}'.encode()).digest()
            first = left+int.from_bytes(jitter[:8],'big')%(right-left+2-frames)
            clips.append({'clip_id':f'{digest}-{first}-{first+frames-1}','interval':[first,first+frames-1]})
        matches.append({'file':'recordings/examples/'+row['file'],'replay_sha256':digest,'group':group,'split':split,
            'previously_examined':previous.get(digest,{}).get('previously_examined',False),
            'stage':31,'players':row['players'],'last_frame':row['last_frame'],'clips':clips})
    result = {'schema':1,'kind':'fox-corpus-split','scope':'Fox/Fox distinct costumes and Fox/Falco; Battlefield human NTSC 4-stock 8-minute singles',
        'slot_mapping':'ascending occupied physical ports; character IDs are not unique in mirrors',
        'frames_per_clip':frames,'clips_per_match':clips_per_match,'skipped':skipped,
        'grouping':'frozen filename-date groups; player disjointness unverified',
        'matches':sorted(matches,key=lambda m:m['replay_sha256'])}
    validate_split_plan(result)
    return result


def hud_check(index, labels, policy='strict'):
    """Per-frame exact UI remains primary; declare readable-HUD corroboration."""
    if policy not in ('strict','corpus-v1'): raise ValueError('unknown HUD evidence policy')
    records = {r['image']:r for r in labels['records']}
    compared = 0; unknown = []; disagreements = []; longest = run = 0
    positive = [r for r in index if r['replay_frame']>0]
    for row in positive:
        record = records[row['capture_image']]
        if record['timer_digits'] is None:
            unknown.append(row['replay_frame']); run+=1; longest=max(longest,run)
        else:
            run=0; compared+=1
            if record['frame']!=row['replay_frame']: disagreements.append(row['replay_frame'])
    coverage = compared/len(positive) if positive else 0
    passed = (bool(positive) and not disagreements and labels['chronological'] and not labels['duplicate_frames']
        and (labels['passed'] if policy=='strict' else coverage>=.9 and longest<=120))
    return {'policy':policy,'passed':passed,'positive_frames':len(positive),'compared':compared,
        'unknown_frames':unknown,'disagreement_frames':disagreements,'coverage':coverage,
        'longest_unknown_run':longest,'full_hud_coverage':not unknown,
        'required_coverage':1. if policy=='strict' else .9,'maximum_unknown_run':0 if policy=='strict' else 120,
        'policy_note':'every selected UI/PNG step still exact; all readable HUDs must agree; unreadable HUDs stay unknown'}


def select_corpus_clips(plan):
    validate_split_plan(plan); buckets={}
    for match in plan['matches']:
        if match['split']=='test': continue
        corpus_ports(match)
        roster=tuple(sorted(p['character'] for p in match['players']))
        for number,clip in enumerate(match['clips']):
            buckets.setdefault((number,match['split'],roster),[]).append({
                **{k:match[k] for k in ('file','replay_sha256','split','group','stage','players')},**clip})
    result=[]
    for number in sorted({k[0] for k in buckets}):
        groups=[sorted(v,key=lambda c:c['clip_id']) for k,v in sorted(buckets.items()) if k[0]==number]
        while any(groups):
            for group in groups:
                if group: result.append(group.pop(0))
    return result
