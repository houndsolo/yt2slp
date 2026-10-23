"""Synthetic scalar/capture reports; real-game evidence is retained separately."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import struct

import pytest

from yt2slp.benchmark import FIELDS, FLOAT_FIELDS, compare_posts, index_rows, observation_rows
from yt2slp.timer_labels import encode, glyphs, recognize, summarize_labels, WIDTH, HEIGHT


def bits(value):
    return struct.unpack('!I',struct.pack('!f',value))[0]


def document():
    return {'schema':1,'settings':{'stage':31},'rows':[
        {'frame':frame,'player':player,'fields':{name:bits(1.0) if name in FLOAT_FIELDS else 1 for name in FIELDS}}
        for frame in (240,241) for player in (0,1)]}


def test_equal_fields_and_exact_frame_coverage_pass():
    a=document();result=compare_posts(a,deepcopy(a),240,241)
    assert result['passed'] and result['expected_player_frames']==4
    assert all(m['compared']==4 and m['rmse']==0 for m in result['metrics'].values())
    assert not result['full_state_equality_measured'] and not result['image_equality_measured']


def test_comparison_preserves_declared_physical_ports_without_relabelling():
    a=document()
    for row in a['rows']:row['player']+=1
    assert compare_posts(a,deepcopy(a),240,241,player_indices=(1,2))['passed']
    b=deepcopy(a);b['rows'].pop(0)
    result=compare_posts(a,b,240,241,player_indices=(1,2))
    assert not result['passed'] and result['missing_candidate']==[(240,1)]
    with pytest.raises(ValueError):compare_posts(a,a,240,241)


@pytest.mark.parametrize('ports',[(1,1),(1,4),(True,2),[1,2]])
def test_comparison_rejects_invalid_player_mapping(ports):
    with pytest.raises(ValueError):compare_posts(document(),document(),240,241,player_indices=ports)


@pytest.mark.parametrize('left,right',[(0x00000000,0x80000000),(0x3f800000,0x3f800001)])
def test_signed_zero_and_one_ulp_are_reported_without_tolerance(left,right):
    a=document();b=deepcopy(a)
    a['rows'][0]['fields']['x']=left;b['rows'][0]['fields']['x']=right
    result=compare_posts(a,b,240,241)
    assert not result['passed'] and result['metrics']['x']['bit_mismatches']==1
    assert result['first_difference']['frame']==240


def test_numeric_error_is_measured_separately_from_exact_gate():
    a=document();b=deepcopy(a);b['rows'][0]['fields']['x']=bits(3.0)
    result=compare_posts(a,b,240,241)
    assert result['metrics']['x']['max_absolute_error']==2
    assert result['metrics']['x']['rmse']==1 and not result['passed']


def test_missing_frames_are_not_replaced_with_best_fitting_offset():
    a=document();b=deepcopy(a)
    for row in b['rows']:row['frame']+=1
    result=compare_posts(a,b,240,241)
    assert not result['passed'] and result['missing_candidate']==[(240,0),(240,1)]


def test_duplicate_keys_invalid_values_and_nonfinite_floats_fail():
    a=document();a['rows'].append(deepcopy(a['rows'][0]))
    with pytest.raises(ValueError,match='duplicate'):index_rows(a)
    for invalid in (True,-1,0x100000000,0x7f800000):
        a=document();a['rows'][0]['fields']['x']=invalid
        with pytest.raises(ValueError):index_rows(a)


def test_settings_cannot_be_silently_ignored_in_official_comparison():
    a=document();b=deepcopy(a);b['settings']['stage']=32
    assert not compare_posts(a,b,240,241)['passed']


def test_observation_phase_uses_declared_frame_and_raw_bits():
    f=[1,3,14,bits(2),bits(3),bits(4),0,0,0,0,bits(5),bits(-1)]
    rows=observation_rows([{'scene_major':2,'scene':2,'match_frame':240,'fighters':[f,f]}])
    assert rows[0]['frame']==240 and rows[0]['fields']['percent']==bits(5)
    with pytest.raises(ValueError,match='scene'):
        observation_rows([{'scene_major':0,'scene':0}])


def test_ambiguous_or_bad_glyphs_stay_unknown():
    a=tuple(i%2==0 for i in range(WIDTH*HEIGHT));b=tuple(not v for v in a)
    assert recognize([a],{'0':[encode(a)],'1':[encode(b)]},.12,.015)['digits']=='0'
    assert recognize([a],{'0':[encode(a)],'1':[encode(a)]},.12,.015) is None
    assert recognize([tuple(False for _ in a)],{'0':[encode(a)],'1':[encode(b)]},.12,.015) is None
    assert glyphs(bytes(20),5,4,2) is None


def test_capture_reports_require_exact_requested_interval_and_file():
    script=Path(__file__).resolve().parents[1]/'scripts/capture_benchmark.py'
    spec=importlib.util.spec_from_file_location('capture_benchmark',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    text='[FILE_PATH] /replay.slp\n'+''.join(f'[CURRENT_FRAME] {i}\n' for i in range(219,322))
    assert module.assess_window(text,219,321,Path('/replay.slp'))
    assert not module.assess_window(text.replace('[CURRENT_FRAME] 240\n',''),219,321,Path('/replay.slp'))
    assert not module.assess_window(text,219,321,Path('/wrong.slp'))


@pytest.mark.parametrize('frames',[[240,None,242],[240,241,241,242],[242,241,240]])
def test_image_coverage_duplicates_and_reverse_order_fail(frames):
    result=summarize_labels([{'frame':f,'image':f'{i}.png'} for i,f in enumerate(frames)],240,242)
    assert not result['passed']


def test_menu_unknowns_do_not_become_inferred_frame_numbers():
    records=[{'frame':None,'image':'menu.png'},*[{'frame':f,'image':f'{f}.png'} for f in range(240,243)]]
    result=summarize_labels(records,240,242)
    assert result['passed'] and result['selected'][240]=='240.png'


def test_absent_settings_cannot_be_reported_as_matching():
    a=document();del a['settings']
    with pytest.raises(ValueError,match='settings'):
        compare_posts(a,a,240,241)
