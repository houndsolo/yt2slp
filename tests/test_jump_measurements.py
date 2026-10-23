"""Synthetic measurement arithmetic/coverage fixtures, not simulated Melee or .slp files."""
import importlib.util
from pathlib import Path
import struct
from dataclasses import replace

import pytest

from yt2slp.backend import Observation

spec=importlib.util.spec_from_file_location('measure_fox_jumps',Path(__file__).resolve().parents[1]/'scripts/measure_fox_jumps.py')
module=importlib.util.module_from_spec(spec)
# The command shares a script helper with the existing reconstruction runner.
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:spec.loader.exec_module(module)
finally:sys.path.pop(0)


def observation(frame,action,y=0,vy=0):
    bits=lambda v:struct.unpack('!I',struct.pack('!f',v))[0]
    fighter=(1,4,action,bits(0),bits(0),bits(y),bits(0),bits(0),bits(vy),bits(0),bits(0),bits(1))
    return Observation(frame+100,2,2,frame,1,(fighter,fighter))


def trace():
    return [observation(239+i,action,y,vy) for i,(action,y,vy) in enumerate([
        (14,0,0),(24,0,0),(24,0,0),(24,0,0),(25,2,2),(25,3,1),(29,1,-2),(42,0,-2),(14,0,0)])]


def test_jump_measurements_keep_takeoff_squat_apex_and_landing_distinct():
    result=module.jump_metrics(trace())
    assert result['jump_squat_frames']==3
    assert [result[k] for k in ('squat_first_frame','squat_last_frame','takeoff_frame','apex_frame','landing_frame')]==[240,242,243,244,246]
    assert result['height_above_baseline']==3 and result['initial_native_vertical_velocity']==2
    assert result['airborne_frames']==3


@pytest.mark.parametrize('fault',['gap','duplicate','no_squat','split_squat','no_takeoff','no_landing','unfinished','air_jump','scene','nonfinite'])
def test_incomplete_or_interrupted_traces_never_become_valid_jump_measurements(fault):
    rows=trace()
    if fault=='gap':del rows[2]
    elif fault=='duplicate':rows[2]=rows[1]
    elif fault=='no_squat':rows=[observation(r.match_frame,14) for r in rows]
    elif fault=='split_squat':rows[2]=observation(241,14)
    elif fault=='no_takeoff':rows[4]=observation(243,42)
    elif fault=='no_landing':rows[7]=observation(246,29)
    elif fault=='unfinished':rows.pop()
    elif fault=='air_jump':rows[5]=observation(244,27)
    elif fault=='scene':rows[0]=replace(rows[0],scene=1)
    elif fault=='nonfinite':rows[5]=observation(244,25,float('nan'))
    with pytest.raises(ValueError):module.jump_metrics(rows)
