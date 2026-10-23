"""Synthetic scalar/capture reports; real-game evidence is retained separately."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import struct

import pytest

from yt2slp.benchmark import FIELDS, FLOAT_FIELDS, compare_posts, index_rows, observation_rows
from yt2slp.benchmark import validate_match_settings
from yt2slp.timer_labels import encode, glyphs, recognize, summarize_labels, WIDTH, HEIGHT


def bits(value):
    return struct.unpack('!I',struct.pack('!f',value))[0]


def document():
    return {'schema':1,'settings':{'stage':31},'rows':[
        {'frame':frame,'player':player,'fields':{name:bits(1.0) if name in FLOAT_FIELDS else 1 for name in FIELDS}}
        for frame in (240,241) for player in (0,1)]}


def explicit_setup():
    return {'stage': 8, 'players': [{'character': 20}, {'character': 0}],
            'ports': [1, 2], 'stock_rules': {'seconds': 480, 'stocks': 4}, 'spawn_points': [0, 1]}


def setup_settings():
    return {'stage': 8, 'seed': 1234, 'timer_type': 2, 'timer_seconds': 480,
            'players': [{'player': 1, 'character': 20, 'costume': 0, 'type': 0},
                        {'player': 2, 'character': 0, 'costume': 0, 'type': 0}]}


def test_explicit_parser_setup_keeps_physical_ports_and_seed_unknown():
    assert validate_match_settings(setup_settings(), explicit_setup()).ports == (1, 2)
    settings = setup_settings();settings['seed'] = 999
    assert validate_match_settings(settings, explicit_setup()).spawn_points == (0, 1)


@pytest.mark.parametrize('field,value', [('stage', 31), ('timer_type', 0), ('timer_seconds', 120), ('players', [])])
def test_explicit_parser_setup_rejects_different_settings(field, value):
    settings = setup_settings();settings[field] = value
    with pytest.raises(ValueError):validate_match_settings(settings, explicit_setup())


def test_explicit_parser_setup_rejects_port_relabelling_and_default_rules():
    settings = setup_settings();settings['players'][0]['player'] = 0
    with pytest.raises(ValueError):validate_match_settings(settings, explicit_setup())
    requested = explicit_setup();requested['stock_rules'] = None
    with pytest.raises(ValueError):validate_match_settings(setup_settings(), requested)


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


def glyph_fixture(bright_background):
    width, height = 22, 12
    pixels = bytearray([255 if bright_background else 0]*(width*height))
    # Two enclosed glyphs with black outlines, on either bright or dark sky.
    for x, pattern in [(3, [(0,0),(0,1),(0,2),(0,3),(1,3),(2,3),(3,3)]),
                       (14, [(0,0),(1,0),(2,0),(3,0),(3,1),(3,2),(3,3)])]:
        for yy in range(1, 8):
            for xx in range(x-1, x+5):pixels[yy*width+xx] = 0
        for xx, yy in pattern:pixels[(yy+2)*width+x+xx] = 255
    return bytes(pixels), width, height


def test_declared_border_policy_removes_white_sky_without_changing_enclosed_glyphs():
    dark, width, height = glyph_fixture(False)
    bright, _, _ = glyph_fixture(True)
    expected = glyphs(dark, width, height, 2)
    assert expected is not None and expected[0] != expected[1]
    assert glyphs(bright, width, height, 2) != expected
    assert glyphs(bright, width, height, 2, discard_border_components=True) == expected
    assert glyphs(dark, width, height, 2, discard_border_components=True) == expected


def test_border_policy_does_not_invent_missing_digits():
    bright, width, height = glyph_fixture(True)
    assert glyphs(bright, width, height, 3, discard_border_components=True) is None
    assert glyphs(bytes([255])*width*height, width, height, 2, discard_border_components=True) is None


def test_unknown_timer_background_policy_is_rejected_before_calibration(tmp_path):
    from yt2slp.timer_labels import calibrate
    with pytest.raises(ValueError, match='background policy'):
        calibrate({'background_policy': 'invent-missing-digits'}, tmp_path)


def test_capture_reports_require_exact_requested_interval_and_file():
    script=Path(__file__).resolve().parents[1]/'scripts/capture_benchmark.py'
    spec=importlib.util.spec_from_file_location('capture_benchmark',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    text='[FILE_PATH] /replay.slp\n'+''.join(f'[CURRENT_FRAME] {i}\n' for i in range(219,322))
    assert module.assess_window(text,219,321,Path('/replay.slp'))
    assert not module.assess_window(text.replace('[CURRENT_FRAME] 240\n',''),219,321,Path('/replay.slp'))
    assert not module.assess_window(text,219,321,Path('/wrong.slp'))
    assert module.capture_bounds(240,300,20)==(219,321)
    assert module.capture_bounds(-39,140,0,True)==(-40,141)
    assert module.capture_bounds(1,17,0,True,-40)==(-40,18)
    assert module.capture_bounds(1,17,0,True,-123)==(-123,18)
    for start, early in [(1, True), (-124, True), (-40, False), (True, True)]:
        with pytest.raises(ValueError):module.capture_bounds(1,17,0,early,start)
    negative='[FILE_PATH] /replay.slp\n'+''.join(f'[CURRENT_FRAME] {i}\n' for i in range(-40,142))
    assert module.assess_window(negative,-40,141,Path('/replay.slp'))
    for first,last,padding,early in [(-39,140,0,False),(-123,140,0,True),(-39,140,-1,True)]:
        with pytest.raises(ValueError):module.capture_bounds(first,last,padding,early)


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
