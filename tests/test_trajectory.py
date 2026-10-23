"""Synthetic protocol/history fixtures; record mocks never create replay files."""
from copy import deepcopy
from pathlib import Path

import pytest

from yt2slp.backend import Observation
from yt2slp.trajectory import observation_document, render_interval, reproduce_prefix, validate_prefix, validate_segments


def state(frame):return Observation(frame+100,2,2,frame,1,((1,4,14,0,0,0,0,0,0,0,0,0),)*2)


def segments():
    return [{'first':239,'last':241,'schedule':{'pad_phases':[
        {'start_after':0,'stick_x':0,'stick_y':0,'button':1024},
        {'start_after':1,'stick_x':0,'stick_y':0,'button':0}]}},
        {'first':241,'last':243,'schedule':{'pad_phases':[
        {'start_after':0,'stick_x':0,'stick_y':0,'button':2048},
        {'start_after':1,'stick_x':0,'stick_y':0,'button':0}]}}]


def prefix():
    return {'schema':1,'kind':'selected-trajectory-prefix','segments':segments(),
        'source_video_sha256':'source-video','native_identities':{'host':'host','game':'game','iso':'iso','boot':'boot'},
        'start_recipe':{'rng_seed':1,'time_base':0,'known_match':{'stage':31,'characters':[2,20]}},
        'last_observation':observation_document(state(243)),'replay_sha256':'a'*64}


class HistoryTransport:
    def __init__(self):self.current=state(239);self.requests=[];self.exports=[]
    def observe(self):return self.current
    def step(self,pads):
        self.requests.append(pads)
        self.current=state(self.current.match_frame+1)
        return self.current
    def record(self,path):self.exports.append(path) # Deliberately writes no file.


def test_joined_history_has_no_extra_neutral_step_or_duplicated_boundary(monkeypatch,tmp_path):
    backend=HistoryTransport()
    monkeypatch.setattr('yt2slp.trajectory.sha256',lambda path:'a'*64)
    output=tmp_path/'unwritten-transport-export'
    reproduce_prefix(backend,prefix(),output)
    assert [p[0].button for p in backend.requests]==[1024,0,2048,0]
    assert backend.current.match_frame==243 and backend.exports==[output]
    assert not output.exists()


@pytest.mark.parametrize('mismatch',['state','replay'])
def test_reproduced_history_must_match_both_state_and_recording(monkeypatch,tmp_path,mismatch):
    document=prefix()
    if mismatch=='state':document['last_observation']['rng']=2
    monkeypatch.setattr('yt2slp.trajectory.sha256',lambda path:'b'*64)
    with pytest.raises(ValueError,match='boundary state|recording bytes'):
        reproduce_prefix(HistoryTransport(),document,tmp_path/'never-written')


@pytest.mark.parametrize('fault',['gap','overlap','boolean','too_long','reversed','missing','outside_phase'])
def test_segments_reject_missing_or_inconsistent_time(fault):
    rows=segments()
    if fault=='gap':rows[1]['first']=242
    elif fault=='overlap':rows[1]['first']=240
    elif fault=='boolean':rows[0]['first']=True
    elif fault=='too_long':rows[1]['last']=842
    elif fault=='reversed':rows.reverse()
    elif fault=='missing':del rows[0]['schedule']
    elif fault=='outside_phase':rows[0]['schedule']['pad_phases'][-1]['start_after']=2
    with pytest.raises(ValueError):validate_segments(rows)


@pytest.mark.parametrize('fault',['source','native','seed','boundary','digest'])
def test_selected_prefix_cannot_be_reused_with_changed_source_recipe_or_native_build(fault):
    document=prefix();recipe={**document['start_recipe'],'checkpoint_frame':243}
    source='source-video';identities=deepcopy(document['native_identities'])
    if fault=='source':source='other-video'
    elif fault=='native':identities['game']='different-game'
    elif fault=='seed':recipe['rng_seed']=2
    elif fault=='boundary':recipe['checkpoint_frame']=244
    elif fault=='digest':document['replay_sha256']='not-a-digest'
    with pytest.raises(ValueError):validate_prefix(document,recipe,source,identities)


def test_prefix_identity_and_render_interval_contract():
    document=prefix()
    validate_prefix(document,{**document['start_recipe'],'checkpoint_frame':243},'source-video',document['native_identities'])
    assert render_interval({'checkpoint_frame':239,'end_frame':301})==[240,300]
    assert render_interval({'checkpoint_frame':319,'end_frame':401,'render_interval':[319,400]})==[319,400]
    with pytest.raises(ValueError):render_interval({'checkpoint_frame':319,'end_frame':401})
    with pytest.raises(ValueError):render_interval({'checkpoint_frame':239,'end_frame':301,'render_interval':[240,301]})
