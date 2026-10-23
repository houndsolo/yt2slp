"""Host/Docker path and plan validation; no emulator or replay fixtures."""
import importlib.util
import json
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('window_runner',Path(__file__).resolve().parents[1]/'scripts/reconstruct_windows.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_host_docker_mapping_preserves_artifact_and_source_roots(tmp_path):
    assert module.host_path('.local/example/file.json',tmp_path)==tmp_path/'.docker-state/local/example/file.json'
    assert module.host_path('/work/.local/example/file.json',tmp_path)==tmp_path/'.docker-state/local/example/file.json'
    assert module.host_path('configs/example.json',tmp_path)==tmp_path/'configs/example.json'
    assert module.logical('/work/.local/runs/example')=='.local/runs/example'
    for invalid in ('/etc/config','../outside','.local/../../outside'):
        with pytest.raises(ValueError):module.host_path(invalid,tmp_path)


def test_dependency_log_lines_cannot_hide_the_actual_runner_report():
    output='dependency warning\n'+json.dumps({'run':'/work/.local/runs/example','passed':True},indent=2)+'\ntrailing dependency warning\n'
    assert module.last_report(output)['run']=='/work/.local/runs/example'
    with pytest.raises(ValueError):module.last_report('{"unrelated": true}\n')


@pytest.mark.parametrize('fault',['source','gap','recipe','render'])
def test_window_plan_rejects_inconsistent_trajectory_before_running_commands(tmp_path,monkeypatch,fault):
    monkeypatch.setattr(module,'host_path',lambda value:tmp_path/value)
    for name,source in [('full','source'),('first','source'),('second','different' if fault=='source' else 'source')]:
        (tmp_path/name).mkdir();(tmp_path/name/'video.json').write_text(json.dumps({'source_sha256':source}))
    for name in ('cues','regions'):(tmp_path/name).write_text('{}')
    common={'rng_seed':1,'time_base':0,'known_match':{'stage':31,'characters':[2,20]}}
    (tmp_path/'one.json').write_text(json.dumps({**common,'checkpoint_frame':239,'end_frame':319}))
    (tmp_path/'two.json').write_text(json.dumps({**common,'checkpoint_frame':320 if fault=='gap' else 319,'end_frame':401,'rng_seed':2 if fault=='recipe' else 1}))
    plan={'schema':1,'kind':'manual-window-plan','video':'full','render_interval':[240,401 if fault=='render' else 400],
        'windows':[{'spec':s,'video':v,'timeline':'cues','regions':'regions'} for s,v in [('one.json','first'),('two.json','second')]]}
    with pytest.raises(ValueError):module.validate_plan(plan)
