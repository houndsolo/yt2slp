from copy import deepcopy
import json
from pathlib import Path

import pytest

from yt2slp.corpus import corpus_ports, hud_check, plan_corpus, select_corpus_clips


def test_mirrors_use_physical_port_order_and_require_distinct_costumes():
    setup={'stage':31,'players':[{'port':3,'character':2,'costume':1},{'port':1,'character':2,'costume':0}]}
    assert corpus_ports(setup)==[1,3]
    setup['players'][0]['costume']=0
    with pytest.raises(ValueError): corpus_ports(setup)


def test_expanded_plan_is_settings_only_preserves_groups_and_has_nonoverlapping_clips():
    old=json.loads((Path(__file__).parents[1]/'configs/learning-corpus-split-v1.json').read_text())
    rows=[]
    for number,match in enumerate(old['matches'][:2]):
        rows.append({'status':'eligible_singles_settings','stage':31,'is_pal':False,'timer_type':2,'timer_seconds':480,
            'capture_date_from_filename':match['group'].removeprefix('capture-date-'),'last_frame':10000,
            'file':Path(match['file']).name,'replay_sha256':match['replay_sha256'],'players':match['players']})
    rows[1]['players']=deepcopy(rows[1]['players'])
    rows[1]['players'][0].update(character=2,costume=0);rows[1]['players'][1].update(character=2,costume=1)
    plan=plan_corpus(rows,old)
    assert plan==plan_corpus(rows,old)
    reserved={m['replay_sha256']:m for m in old['matches']}
    for m in plan['matches']:
        assert m['split']==reserved[m['replay_sha256']]['split']
        intervals=[c['interval'] for c in m['clips']]
        assert all(b-a+1==1200 and a>=601 and b<=9880 for a,b in intervals)
        assert all(b<c for (a,b),(c,d) in zip(intervals,intervals[1:]))
    bad=deepcopy(rows);bad[0]['timer_seconds']=180;bad[1]['last_frame']=1000
    with pytest.raises(ValueError):plan_corpus(bad,old)


def test_real_frozen_corpus_excludes_tests_from_render_selection():
    plan=json.loads((Path(__file__).parents[1]/'configs/learning-corpus-split-v3.json').read_text())
    clips=select_corpus_clips(plan)
    assert len(clips)==300
    assert not {c['replay_sha256'] for c in clips}&{m['replay_sha256'] for m in plan['matches'] if m['split']=='test'}
    first=clips[:4]
    assert {(c['split'],tuple(sorted(p['character'] for p in c['players']))) for c in first}=={
        ('train',(2,2)),('train',(2,20)),('validation',(2,2)),('validation',(2,20))}


def hud_fixture(unknown=(),wrong=()):
    index=[{'replay_frame':i,'capture_image':f'{i}.png'} for i in range(1,201)]
    labels={'records':[{'image':f'{i}.png','frame':None if i in unknown else i+1 if i in wrong else i,
        'timer_digits':None if i in unknown else 'literal'} for i in range(1,201)],
        'chronological':True,'duplicate_frames':[],'passed':not unknown and not wrong}
    return index,labels


def test_mass_hud_policy_retains_unknowns_but_never_accepts_disagreement():
    index,labels=hud_fixture(unknown=(3,90))
    result=hud_check(index,labels,'corpus-v1')
    assert result['passed'] and result['compared']==198 and result['unknown_frames']==[3,90]
    assert not result['full_hud_coverage'] and not hud_check(index,labels,'strict')['passed']
    index,labels=hud_fixture(unknown=(3,),wrong=(70,))
    assert not hud_check(index,labels,'corpus-v1')['passed']


def test_mass_hud_policy_rejects_a_long_occlusion_even_with_high_overall_coverage():
    index=[{'replay_frame':i,'capture_image':str(i)} for i in range(1,1801)]
    labels={'records':[{'image':str(i),'frame':None if i<=130 else i,
        'timer_digits':None if i<=130 else 'literal'} for i in range(1,1801)],
        'chronological':True,'duplicate_frames':[],'passed':False}
    report=hud_check(index,labels,'corpus-v1')
    assert report['coverage']>.9 and report['longest_unknown_run']==130
    assert not report['passed']
    index,labels=hud_fixture(unknown=range(1,30))
    assert not hud_check(index,labels,'corpus-v1')['passed']
