"""Synthetic controller echoes/counters, never gameplay or replay-file fixtures."""
import json
import struct

import pytest

from yt2slp.backend import Observation, RecordingStatus
from yt2slp.evidence import Evidence, Provenance
from yt2slp.match import match_from_document
from yt2slp.search import bounded_search, run_recorded_schedule, schedule_document, schedule_from_dict
from yt2slp.timeline import Cue, Sample, load_timeline, score_timeline


def bits(value):return struct.unpack('!I',struct.pack('!f',value))[0]


def program(left=-40,right=40):
    return {'port_programs':[{'port':port,'pad_phases':[
        {'start_after':0,'stick_x':x,'stick_y':0,'button':0}]} for port,x in [(1,left),(2,right)]]}


def evidence(value):return Evidence(value,Provenance.INFERRED,'synthetic cue for transport testing')


def test_explicit_recipe_binds_physical_players_and_stock_rules():
    match=match_from_document({'stage':8,'players':[{'character':20},{'character':0}],
        'ports':[1,2],'stock_rules':{'seconds':480,'stocks':4}})
    assert match.ports==(1,2) and match.stock_rules.seconds==480
    assert match.native_argument()=='8 20 0 0 9 0 0 0 9 ports 1 2'
    match=match_from_document({'stage':8,'players':[{'character':20},{'character':0}],
        'ports':[1,2],'stock_rules':{'seconds':480,'stocks':4},'spawn_points':[0,1]})
    assert match.native_argument().endswith('ports 1 2 spawns 0 1')


@pytest.mark.parametrize('fault',['missing_ports','unknown_player','unknown_rule','duplicate_port','duplicate_spawn','bad_spawn'])
def test_recipe_rejects_missing_or_misbound_setup(fault):
    doc={'stage':8,'players':[{'character':20},{'character':0}],
        'ports':[1,2],'stock_rules':{'seconds':480,'stocks':4}}
    if fault=='missing_ports':del doc['ports']
    elif fault=='unknown_player':doc['players'][0]['fighter_kind']=22
    elif fault=='unknown_rule':doc['stock_rules']['speed']=2
    elif fault=='duplicate_port':doc['ports']=[1,1]
    elif fault=='duplicate_spawn':doc['spawn_points']=[0,0]
    elif fault=='bad_spawn':doc['spawn_points']=[0,4]
    with pytest.raises(ValueError):match_from_document(doc)


def samples():
    return (Sample(0,(-1,),evidence([-1]),(
        Cue(0,'horizontal_order',evidence(['left'])),Cue(1,'horizontal_order',evidence(['right']))),
        'slippi-replay'),)


class EchoPeer:
    """Echo pad axes in synthetic fields; no physics, actions or replay writer."""
    def __init__(self):self.key=-2;self.x=[0,0];self.captures=0;self.restores=0
    def observe(self):
        empty=(0,)*12
        actors=tuple((1,4,14,0,bits(x),0,0,0,0,0,0,bits(1)) for x in self.x)
        return Observation(self.key+130,2,2,max(0,self.key),0,(empty,*actors,empty,empty,empty))
    def recording_status(self):return RecordingStatus(self.key,False)
    def step(self,pads):
        assert [p.err for p in pads]==[-1,0,0,-1]
        self.key+=1;self.x=[pads[1].stick_x,pads[2].stick_x]
        return self.observe()
    def capture(self):self.captures+=1;self.saved=(self.key,self.x.copy());return b'echo'
    def restore(self,handle):
        assert handle==b'echo'
        self.key,self.x=self.saved[0],self.saved[1].copy();self.restores+=1
    def record(self,path):raise AssertionError('search cannot fabricate a replay')


def test_simultaneous_physical_program_roundtrip_and_independent_release():
    document=program()
    document['port_programs'][0]['pad_phases']=[
        {'start_after':1,'stick_x':0,'stick_y':0,'button':1024},
        {'start_after':3,'stick_x':0,'stick_y':0,'button':0}]
    sequence=schedule_from_dict(document)
    assert schedule_document(sequence)==document
    assert schedule_from_dict(json.loads(json.dumps(document)))==sequence
    values=[sequence.pads(i) for i in range(5)]
    assert [p[1].button for p in values]==[0,1024,1024,0,0]
    assert [p[2].stick_x for p in values]==[40]*5
    assert all([p.err for p in pads]==[-1,0,0,-1] for pads in values)


@pytest.mark.parametrize('fault',['same_port','invalid_port','missing','pause','extra','only_one'])
def test_invalid_player_programs_are_rejected(fault):
    document=program()
    if fault=='same_port':document['port_programs'][1]['port']=1
    elif fault=='invalid_port':document['port_programs'][1]['port']=4
    elif fault=='missing':del document['port_programs'][0]['pad_phases']
    elif fault=='pause':document['port_programs'][0]['pad_phases'][0]['button']=0x1000
    elif fault=='extra':document['port_programs'][0]['cpu']=False
    elif fault=='only_one':document['port_programs'].pop()
    with pytest.raises(ValueError):schedule_from_dict(document)


def test_signed_replay_keys_remain_separate_from_zero_match_counter():
    peer=EchoPeer();states,keys=run_recorded_schedule(peer,schedule_from_dict(program()),3)
    assert keys==(-2,-1,0,1)
    assert [s.match_frame for s in states]==[0,0,0,1]
    assert score_timeline(samples(),states,frame_keys=keys,player_ports=(1,2))['accepted']
    with pytest.raises(ValueError,match='clocks'):score_timeline(samples(),states,player_ports=(1,2))


def test_two_player_search_reruns_selected_branch_after_later_rejection(tmp_path):
    peer=EchoPeer();candidates=tuple(schedule_from_dict(program(a,b)) for a,b in [(-40,40),(-80,80),(40,-40)])
    result=bounded_search(peer,samples(),candidates,3,tmp_path/'trials',frame_clock='slippi-replay',player_ports=(1,2))
    assert result['passed'] and result['accepted_indices']==[0,1]
    assert result['window']==[-2,1] and result['frame_clock']=='slippi-replay'
    assert result['player_ports']==(1,2) and peer.x==[-40,40]
    assert peer.captures==1 and peer.restores==4
    saved=json.loads((tmp_path/'trials/000.json').read_text())
    assert saved['replay_frame_keys']==[-2,-1,0,1]
    assert [s['match_frame'] for s in saved['states']]==[0,0,0,1]
    assert not list(tmp_path.rglob('*.slp'))


def test_failed_two_player_search_restores_prefix_and_writes_no_replay(tmp_path):
    peer=EchoPeer()
    result=bounded_search(peer,samples(),(schedule_from_dict(program(40,-40)),),3,tmp_path/'trials',
        frame_clock='slippi-replay',player_ports=(1,2))
    assert not result['passed'] and peer.key==-2 and peer.x==[0,0]
    assert not list(tmp_path.rglob('*.slp'))


def test_ports_and_frame_clock_must_match_before_checkpoint_capture(tmp_path):
    for clock,ports in [('native-match',(1,2)),('slippi-replay',(0,1))]:
        peer=EchoPeer()
        with pytest.raises(ValueError):bounded_search(peer,samples(),(schedule_from_dict(program()),),3,
            tmp_path/'uncreated',frame_clock=clock,player_ports=ports)
        assert peer.captures==0 and not (tmp_path/'uncreated').exists()


def test_negative_annotation_keys_require_explicit_replay_clock():
    video={'schema':1,'kind':'local-video','source_sha256':'synthetic','frames':[{'image_sha256':'image'}]}
    doc={'schema':1,'kind':'manual-visual-cues','video_sha256':'synthetic','frame_clock':'slippi-replay',
        'samples':[{'video_frame':0,'image_sha256':'image','alignment':{'value':[-1],
        'provenance':'inferred','source':'synthetic frame annotation'},'cues':[{'player':0,'field':'damage',
        'evidence':{'value':[0],'provenance':'observed','source':'synthetic annotation'}}]}]}
    assert load_timeline(doc,video)[0].frame_clock=='slippi-replay'
    del doc['frame_clock']
    with pytest.raises(ValueError):load_timeline(doc,video)


def test_recording_counter_gaps_are_never_filled():
    class Gap(EchoPeer):
        def step(self,pads):self.key+=1;return super().step(pads)
    with pytest.raises(ValueError,match='recorded frame'):
        run_recorded_schedule(Gap(),schedule_from_dict(program()),2)
