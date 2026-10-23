"""Control argument/split guards without running Docker, SSH or game assets."""
import json
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/learning'))
from manage import docker_command, inspect, validate_config, launch


def test_worker_is_detached_local_and_bound_to_only_the_selected_gpu():
    config = json.loads((ROOT/'configs/vision-v100.json').read_text())
    validate_config(config)
    command = docker_command(config,ROOT/'configs/vision-v100.json','training',200000)
    assert '--detach' in command and '--restart=no' in command and '--network=none' in command
    assert command[command.index('--gpus')+1]=='device='+config['gpu']
    assert command[-2:]==['--steps','200000']
    assert 'ssh' not in command and not any('10.12.0.10' in s for s in command)
    assert config['python'] in command


def test_controller_never_removes_a_foreign_container():
    result = type('Result',(),{'returncode':0,'stdout':json.dumps([{'Config':{'Labels':{}},'State':{'Running':False}}])})()
    with patch('manage.subprocess.run',return_value=result) as call:
        with pytest.raises(ValueError,match='another application'): inspect('training')
        assert call.call_count==1


def test_review_uses_render_dependencies_and_blocks_training_until_finished():
    config = json.loads((ROOT/'configs/vision-v100.json').read_text())
    command = docker_command(config,ROOT/'configs/vision-v100.json','review')
    assert config['render_image'] in command and 'tools/learning/review_run.py' in command
    assert '--network=none' in command and '--detach' in command
    with patch('manage.inspect',side_effect=lambda kind:{'Running':True} if kind=='review' else None):
        with pytest.raises(ValueError,match='review'): launch(config,ROOT/'configs/vision-v100.json','training')


@pytest.mark.parametrize('key,value',[('gpu','all'),('data_directory','../elsewhere'),('evaluate_every',0),('context_frames',4)])
def test_invalid_control_configuration_fails(key,value):
    config = json.loads((ROOT/'configs/vision-v100.json').read_text()); config[key]=value
    with pytest.raises(ValueError): validate_config(config)


def test_date_split_retains_pilot_reservations_without_reading_targets():
    make_plan = runpy.run_path(str(ROOT/'scripts/plan_vision_dataset.py'))['plan_matches']
    reserved = json.loads((ROOT/'configs/learning-pilot-split-v1.json').read_text())
    entries = [{'status':'eligible_singles_settings','stage':31,'players':[{'character':2},{'character':20}],
        'capture_date_from_filename':date,'last_frame':1000,'file':f'Game_{date}.slp','replay_sha256':m['replay_sha256']}
        for date,m in zip(('20260622','20260623'),reserved['matches'])]
    # A second same-date match must inherit the group's existing reservation.
    entries.append({**entries[1],'file':'another.slp','replay_sha256':'a'*64})
    entries.append({**entries[0],'status':'skip_multiplayer','replay_sha256':'b'*64})
    result = make_plan(entries,reserved)
    assert len(result['matches'])==3
    assert [m['split'] for m in result['matches']]==['train','validation','validation']
