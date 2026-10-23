"""Declared controller boundaries, not synthetic game/replay generation."""
from pathlib import Path
from copy import deepcopy
import subprocess
import sys

import pytest

from yt2slp.match import NEUTRAL_PADS
from yt2slp.reference_cases import REFERENCE_CASES, validate_reference_report


@pytest.mark.parametrize('name,neutral,total,axis', [
    ('fox-falco-battlefield-horizontal-v1',240,420,80),
    ('fox-falco-battlefield-left-delayed-v1',246,320,-80),
])
def test_known_source_controls_preserve_poll_boundaries_and_other_ports(name,neutral,total,axis):
    case=REFERENCE_CASES[name]
    assert case.total_steps == total
    assert all(case.pads(i)==NEUTRAL_PADS for i in range(neutral))
    assert case.pads(neutral)[0].stick_x == axis and case.pads(total-1)[0].stick_x == axis
    assert case.pads(neutral)[1:] == NEUTRAL_PADS[1:]
    for invalid in (-1,total,True,1.5):
        with pytest.raises(ValueError):case.pads(invalid)


def test_unknown_source_case_is_rejected_before_attempting_game_boot():
    script=Path(__file__).resolve().parents[1]/'scripts/record_benchmark.py'
    result=subprocess.run([sys.executable,str(script),'--case','not-supported'],capture_output=True,text=True)
    assert result.returncode==2 and 'invalid choice' in result.stderr


def validated_report():
    return {'case':'fox-falco-battlefield-left-delayed-v1','passed':True,
            'native_vs_official_postframes':{'passed':True},'native_observation_phase_check':{'passed':True},
            'frame_alignment':{'passed':True,'interval':[240,300]},
            'native_replay_sha256':'replay-identity','reference_clip_sha256':'clip-identity',
            'reference_clip':{'nb_read_frames':'61','r_frame_rate':'60/1','width':642,'height':528,'codec_name':'ffv1'}}


def test_source_preparation_requires_the_exact_validated_replay_and_clip():
    report=validated_report()
    validate_reference_report(report,'replay-identity','clip-identity')
    for replay,clip in [('different-replay','clip-identity'),('replay-identity','different-clip')]:
        with pytest.raises(ValueError,match='identity'):validate_reference_report(report,replay,clip)


def test_multiphase_source_includes_real_release_and_reversal_boundaries():
    case=REFERENCE_CASES['fox-falco-battlefield-right-release-left-v1']
    assert case.total_steps==320
    assert [case.pads(i)[0].stick_x for i in (0,239,240,255,256,263,264,319)] == [0,0,80,80,0,0,-80,-80]
    assert all(case.pads(i)[1:]==NEUTRAL_PADS[1:] for i in range(320))
    for invalid in (-1,320,True):
        with pytest.raises(ValueError):case.pads(invalid)


def test_jump_source_releases_button_without_changing_axes_or_other_ports():
    case=REFERENCE_CASES['fox-falco-battlefield-jump-v1']
    assert case.total_steps==320
    assert [case.pads(i)[0].button for i in (0,243,244,245,246,319)] == [0,0,0x400,0x400,0,0]
    assert all(case.pads(i)[0].stick_x==case.pads(i)[0].stick_y==0 for i in range(320))
    assert all(case.pads(i)[1:]==NEUTRAL_PADS[1:] for i in range(320))


def test_two_window_reference_requires_its_full_declared_span():
    case=REFERENCE_CASES['fox-falco-battlefield-two-jumps-v1']
    assert case.clip_interval==(240,400) and case.total_steps==480
    assert [case.pads(i)[0].button for i in (243,244,245,246,323,324,327,328)]==[0,1024,1024,0,0,1024,1024,0]
    report=validated_report();report['case']='fox-falco-battlefield-two-jumps-v1'
    with pytest.raises(ValueError):validate_reference_report(report,'replay-identity','clip-identity')
    report['frame_alignment']['interval']=[240,400]
    report['reference_clip']['nb_read_frames']='161'
    validate_reference_report(report,'replay-identity','clip-identity')


@pytest.mark.parametrize('component',['passed','native_vs_official_postframes','native_observation_phase_check','frame_alignment','geometry','rate'])
def test_incomplete_reference_is_not_prepared_as_a_valid_source(component):
    report=deepcopy(validated_report())
    if component=='passed':report['passed']=False
    elif component=='geometry':report['reference_clip']['width']=640
    elif component=='rate':report['reference_clip']['r_frame_rate']='30/1'
    else:report[component]['passed']=False
    with pytest.raises(ValueError):validate_reference_report(report,'replay-identity','clip-identity')
