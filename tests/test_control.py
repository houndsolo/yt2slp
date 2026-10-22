"""Protocol/lifecycle checks with synthetic peers, never gameplay validation."""
from dataclasses import replace
from pathlib import Path
import sys
import time

import pytest

from yt2slp.backend import BackendError, NativeLinuxBackend, RunConfig, UnsupportedOperation
from yt2slp.match import MatchConfig, PlayerConfig, PadInput, NEUTRAL_PADS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def configured(tmp_path):
    # Compiled with the same RetraceControl implementation as melee_headless.
    host = ROOT / "build/headless/headless_control_fixture"
    assert host.is_file(), "build the asset-independent host first: bash scripts/setup.sh"
    for name in ("game.so", "disc.iso", "boot.txt"):
        (tmp_path / name).touch()
    with NativeLinuxBackend() as backend:
        backend.initialize(RunConfig(host, tmp_path / "game.so", tmp_path / "disc.iso", tmp_path / "runs", match=MatchConfig()))
        yield backend, tmp_path / "boot.txt"


def test_native_protocol_retains_session_applies_all_inputs_and_pauses(configured):
    backend, script = configured
    first = backend.start(script, timeout=2)
    process = backend._session.process
    assert first.retrace == 1
    time.sleep(0.03)
    assert backend.observe() == first
    for retrace, button in enumerate((0x100, 0, 0x400), 2):
        state = backend.step((PadInput(button=button, stick_x=-128), *NEUTRAL_PADS[1:]))
        assert state.retrace == retrace
        assert state.fighters[0][4] == sum((0x100, 0, 0x400)[:retrace - 1])
        assert backend._session.process is process and process.poll() is None
        assert backend.observe() == state
    assert "-128" in (backend.last_run_dir / "inputs.txt").read_text()
    assert '"stage": 31' in (backend.last_run_dir / "config.json").read_text()
    backend.close()
    assert process.poll() == 0
    backend.close()
    with pytest.raises(BackendError, match="start"):
        backend.step(NEUTRAL_PADS)


def test_restart_and_initialize_reap_previous_process(configured):
    backend, script = configured
    backend.start(script, timeout=2)
    process = backend._session.process
    directory = backend.last_run_dir
    backend.start(script, timeout=2)
    assert process.poll() == 0 and backend.last_run_dir != directory
    process = backend._session.process
    backend.initialize(backend.config)
    assert process.poll() == 0 and not backend.observations


def test_validation_does_not_advance_live_session(configured):
    backend, script = configured
    first = backend.start(script, timeout=2)
    for pads in ({}, (), NEUTRAL_PADS[:3], (*NEUTRAL_PADS[:3], object())):
        with pytest.raises(BackendError, match="four PadInput"):
            backend.step(pads)
        assert backend.observe() == first
    for op in (backend.capture, lambda: backend.restore(b""), lambda: backend.record(script.parent / "never.slp")):
        with pytest.raises(UnsupportedOperation):
            op()
    assert not (script.parent / "never.slp").exists()


@pytest.mark.parametrize("kwargs", [{"stage": 30}, {"stage": True}, {"stage": 33}, {"players": ()}, {"players": (2, 20)}])
def test_invalid_match(kwargs):
    with pytest.raises(ValueError):
        MatchConfig(**kwargs)


@pytest.mark.parametrize("kwargs", [{"character": -1}, {"character": 26}, {"costume": 4}, {"cpu": 2}, {"cpu_level": 0}])
def test_invalid_player(kwargs):
    with pytest.raises(ValueError):
        PlayerConfig(**kwargs)


@pytest.mark.parametrize("kwargs", [{"button": -1}, {"button": 65536}, {"stick_x": 128}, {"sub_y": -129},
                                    {"trigger_l": 256}, {"analog_b": 1.5}, {"err": 1}, {"stick_y": True}])
def test_invalid_pad(kwargs):
    with pytest.raises(ValueError):
        PadInput(**kwargs)


def test_match_argument_uses_external_ids_and_preserves_player_settings():
    assert MatchConfig(32, (PlayerConfig(2, 1), PlayerConfig(20, 3, 1, 4))).native_argument() == "32 2 1 0 9 20 3 1 4"


@pytest.mark.parametrize("limit,timeout", [(0, 1), (2**32, 1), (True, 1), (1, 0), (1, float("nan"))])
def test_bad_start_limits(configured, limit, timeout):
    backend, script = configured
    with pytest.raises(BackendError):
        backend.start(script, boot_limit=limit, timeout=timeout)
    assert backend.last_run_dir is None


def test_start_requires_explicit_fixed_match(configured):
    backend, script = configured
    backend.initialize(replace(backend.config, match=None))
    with pytest.raises(BackendError, match="MatchConfig"):
        backend.start(script)


@pytest.mark.parametrize("mode", ["version", "truncated", "bad_state", "menu", "timeout", "gap", "observe", "exit"])
def test_bad_peer_aborts_clears_state_and_reaps(configured, tmp_path, mode, monkeypatch):
    import yt2slp.native_control as transport
    backend, script = configured
    peer = tmp_path / "bad_peer"
    peer.write_text(f'''#!{sys.executable}
import socket, sys, time
mode = {mode!r}
s = socket.socket(fileno=int(sys.argv[sys.argv.index('--control-fd') + 1]))
def send(line): s.sendall((line + '\\n').encode())
def state(retrace=1):
    return 'STATE ' + ','.join(map(str, [retrace, 2, 2, 1, 0] + [1] * 72))
print('fixture diagnostic', flush=True)
if mode == 'exit': sys.exit(9)
if mode == 'timeout': time.sleep(10)
if mode == 'truncated': s.sendall(b'MUCONTROL'); sys.exit(0)
send('WRONG 1' if mode == 'version' else 'MUCONTROL 1')
send('STATE 1,2' if mode == 'bad_state' else state().replace('1,2,2,1,0', '1,0,0,0,0') if mode == 'menu' else state())
s.recv(4096)
send(state(3) if mode == 'gap' else state(2))
time.sleep(10)
''')
    peer.chmod(0o700)
    backend.initialize(replace(backend.config, host=peer))
    processes = []
    popen = transport.subprocess.Popen
    def track(*a, **kw):
        child = popen(*a, **kw)
        processes.append(child)
        return child
    monkeypatch.setattr(transport.subprocess, "Popen", track)
    with pytest.raises(BackendError, match="native control failed"):
        backend.start(script, timeout=0.3)
        if mode == "gap":
            backend.step(NEUTRAL_PADS)
        else:
            backend.observe()
    assert backend._session is None and not backend.observations
    assert processes and processes[0].poll() is not None
    assert "fixture diagnostic" in (backend.last_run_dir / "host.log").read_text()
