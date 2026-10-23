"""Exercise argument transport without requiring Docker or exposing a real GPU."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.fixture
def docker_command(tmp_path):
    scripts, binaries = tmp_path/'scripts', tmp_path/'bin'
    scripts.mkdir(); binaries.mkdir()
    script = scripts/'docker.sh'
    shutil.copy2(Path(__file__).resolve().parents[1]/'scripts/docker.sh', script)
    fake = binaries/'docker'
    fake.write_text(f'#!{sys.executable}\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
    fake.chmod(0o755)
    env = {**os.environ, 'PATH': str(binaries)+os.pathsep+os.defpath}
    env.pop('YT2SLP_ISO', None)
    env.pop('CODEX_PROXY_CERT', None)

    def run(selector):
        return subprocess.run(['bash', str(script), 'run', 'python', '-V'],
            env={**env, 'YT2SLP_GPU': selector}, capture_output=True, text=True)
    return run


@pytest.mark.parametrize('selector', ['', '1', 'GPU-11111111-2222-3333-4444-555555555555'])
def test_gpu_is_explicit_and_selects_exactly_one_device(docker_command, selector):
    result = docker_command(selector)
    assert result.returncode == 0, result.stderr
    args = json.loads(result.stdout)
    if selector:
        assert args[args.index('--gpus')+1] == 'device='+selector
        assert 'NVIDIA_DRIVER_CAPABILITIES=compute,utility' in args
    else:
        assert '--gpus' not in args
    assert args[-3:] == ['yt2slp-dev:gcc14', 'python', '-V']


@pytest.mark.parametrize('selector', ['all', '0,1', '1 --privileged', 'GPU-notvalid'])
def test_invalid_gpu_selector_fails_before_running_docker(docker_command, selector):
    result = docker_command(selector)
    assert result.returncode == 2 and not result.stdout
    assert 'select one numeric GPU index or NVIDIA GPU UUID' in result.stderr
