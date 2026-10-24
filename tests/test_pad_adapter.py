"""Synthetic calibration metadata only; actual gameplay checks use local ISO runs."""
from copy import deepcopy
import pytest

from yt2slp.pad_adapter import infer_lag,axis_candidates,exact_single_axis_pad,decode_controlled_row,compare_control_labels


def test_lag_is_measured_from_request_boundaries_on_a_common_interval():
    requests=[{'boundary_frame':100+i,'pads':[{'button':(0,256,0,1024,512,0,0)[i%7]},
        {'button':(0,2048,512,0,0)[i%5]}]} for i in range(25)]
    keyed={r['boundary_frame']:r for r in requests}
    rows=[{'frame':f,'port':port,'value':keyed[f-2]['pads'][slot]['button'] if f-2 in keyed else 0}
        for f in range(100,127) for slot,port in enumerate((1,3))]
    result=infer_lag(requests,rows,(1,3),lambda r:r['value'],lambda p:p['button'])
    assert result['boundary_to_replay_lag']==2
    assert all(result['diagnostics'][str(i)]['mismatches'] for i in (0,1,3,4))
    counts={r['compared'] for r in result['diagnostics'].values()};assert counts=={42}
    with pytest.raises(ValueError,match='missing'):
        infer_lag(requests,rows[12:],(1,3),lambda r:r['value'],lambda p:p['button'])


def test_neutral_data_cannot_claim_to_have_calibrated_a_lag():
    requests=[{'boundary_frame':i,'pads':[{'button':0}]} for i in range(10)]
    rows=[{'frame':i,'port':0,'value':0} for i in range(10)]
    with pytest.raises(ValueError,match='ambiguous'):
        infer_lag(requests,rows,(0,),lambda r:r['value'],lambda p:p['button'])


@pytest.fixture
def profile():
    return {'axis_samples':[{'axis':axis,'raw':raw,'effective':value}
        for axis in ('stick_x','stick_y') for raw,value in ((0,0.),(10,0.),(24,.3),(30,.375),(80,1.),(127,1.))]}


def test_lookup_preserves_measured_dead_zones_and_refuses_unreachable_bins(profile):
    assert axis_candidates(profile,'stick_x',10)[0]['raw']==24
    assert exact_single_axis_pad(profile,'stick_x',0.).stick_x==0
    assert exact_single_axis_pad(profile,'stick_x',1.).stick_x==80
    with pytest.raises(ValueError,match='no measured'):axis_candidates(profile,'stick_x',9)
    with pytest.raises(ValueError,match='not measured'):exact_single_axis_pad(profile,'stick_x',.25)


def row():
    return {'physical':{'values':{'buttons':1024},'mask':{'buttons':True}},
        'effective':{'values':{'stick_x':1.,'stick_y':0.,'cstick_x':0.,'cstick_y':0.,'trigger':0.},
            'mask':dict.fromkeys(('stick_x','stick_y','cstick_x','cstick_y','trigger'),True)}}


def test_controlled_inverse_maps_holds_without_synthesizing_edge_labels(profile):
    pad=decode_controlled_row(profile,row())
    assert pad.button==1024 and pad.stick_x==80 and pad.stick_y==0


@pytest.mark.parametrize('change',['start','shoulder','diagonal','trigger','masked'])
def test_unsupported_composition_is_explicit(profile,change):
    sample=deepcopy(row())
    if change=='start':sample['physical']['values']['buttons']=4096
    if change=='shoulder':sample['physical']['values']['buttons']=64
    if change=='diagonal':sample['effective']['values']['stick_y']=1.
    if change=='trigger':sample['effective']['values']['trigger']=1.
    if change=='masked':sample['effective']['mask']['stick_x']=False
    with pytest.raises(ValueError):decode_controlled_row(profile,sample)


def test_playback_control_gate_keeps_physical_diagnostics_and_exact_signed_keys_separate():
    sample=row();sample.update(frame=-1,port=0)
    sample['effective']['values']['buttons']=1024;sample['effective']['mask']['buttons']=True
    sample['physical']['values'].update(trigger_l=0.,trigger_r=0.,raw_stick_x=80)
    sample['physical']['mask'].update(trigger_l=True,trigger_r=True,raw_stick_x=True)
    other=deepcopy(sample);other['port']=1
    reference={'settings':{'players':[{'port':0},{'port':1}]},'rows':[sample,other]}
    candidate=deepcopy(reference);candidate['rows'][0]['physical']['values']['buttons']=0
    report=compare_control_labels(reference,candidate,-1,-1)
    assert report['passed'] and not report['groups']['physical']['passed']
    candidate['rows'][1]['effective']['values']['stick_x']=.5
    assert not compare_control_labels(reference,candidate,-1,-1)['passed']
    candidate=deepcopy(reference);candidate['rows'][0]['frame']=0
    assert not compare_control_labels(reference,candidate,-1,-1)['passed']
    with pytest.raises(ValueError):compare_control_labels(reference,reference,0,-1)
