"""Contract tests use synthetic CSV, not simulated gameplay or replay evidence."""
from pathlib import Path
from dataclasses import replace
import subprocess

import pytest

from yt2slp.backend import BackendError, NativeLinuxBackend, RunConfig, UnsupportedOperation, decode_float_bits, read_observations
from yt2slp.evidence import Evidence, Provenance


def digest_row(retrace=1, frame=1):
    return ",".join(map(str, [retrace, 2, 3, frame, 123] + [1, 4, 14, 0x3F800000, 0xBF800000, 0, 0, 0, 0, 0, 0, 0x3F800000] * 6)) + "\n"


@pytest.fixture
def configured(tmp_path):
    # Files are transport placeholders only: these tests never claim to boot Melee.
    for name in ("host", "game.so", "disc.iso", "input.txt"):
        (tmp_path / name).touch()
    (tmp_path / "host").chmod(0o700)
    backend = NativeLinuxBackend()
    backend.initialize(RunConfig(tmp_path / "host", tmp_path / "game.so", tmp_path / "disc.iso", tmp_path / "runs"))
    return backend, tmp_path / "input.txt"


def test_digest_preserves_bits_and_provenance(tmp_path):
    path = tmp_path / "state.csv"
    path.write_text(digest_row())
    observation, = read_observations(path)
    assert observation.fighters[0][4] == 0xBF800000
    assert decode_float_bits(observation.fighters[0][4]) == -1.0
    assert observation.as_evidence().provenance is Provenance.INFERRED
    assert len(observation.fighters) == 6


@pytest.mark.parametrize("data", ["", "1,2,3\n", digest_row(2), digest_row() * 2,
                                   digest_row().replace("123", "-1"), digest_row().replace("123", "4294967296"),
                                   digest_row().replace("123", "nan")])
def test_invalid_digest_is_not_success(tmp_path, data):
    path = tmp_path / "state.csv"
    path.write_text(data)
    with pytest.raises(BackendError):
        read_observations(path)


def test_missing_digest(tmp_path):
    with pytest.raises(BackendError, match="invalid state digest"):
        read_observations(tmp_path / "missing")


@pytest.mark.parametrize("value,kind", [(0, Provenance.UNKNOWN), (None, Provenance.OBSERVED), (None, Provenance.INFERRED)])
def test_unknown_is_not_a_default_value(value, kind):
    with pytest.raises(ValueError):
        Evidence(value, kind, "fixture")


def test_evidence_source_required():
    assert Evidence(None, Provenance.UNKNOWN, "hidden RNG not visible in video").value is None
    with pytest.raises(ValueError):
        Evidence(1, Provenance.OBSERVED, "")


def test_unsupported_operations_create_no_replay(tmp_path):
    backend = NativeLinuxBackend()
    output = tmp_path / "result.slp"
    for operation in (lambda: backend.record(output),):
        with pytest.raises(UnsupportedOperation):
            operation()
    with pytest.raises(BackendError, match="no successful"):
        backend.observe()
    assert not output.exists()


def test_missing_artifacts_block_initialization(tmp_path):
    backend = NativeLinuxBackend()
    with pytest.raises(BackendError, match="missing headless host"):
        backend.initialize(RunConfig(*(tmp_path / str(i) for i in range(4))))
    with pytest.raises(BackendError, match="initialize"):
        backend.run_script(tmp_path / "script", 1)


@pytest.mark.parametrize('boundary', ['auto', None, True])
def test_unsupported_seed_boundary_is_rejected(configured, boundary):
    backend, _ = configured
    with pytest.raises(BackendError, match='rng_seed_boundary'):
        backend.initialize(replace(backend.config, rng_seed_boundary=boundary))


def test_explicit_game_start_seed_boundary_survives_configuration_and_batch_transport(configured, monkeypatch):
    backend, script = configured
    backend.initialize(replace(backend.config, rng_seed=33480, rng_seed_boundary='slippi-game-start'))
    calls = []
    def emit(command, **kwargs):
        calls.append(command)
        Path(command[command.index('--state-digest')+1]).write_text(digest_row())
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(subprocess, 'run', emit)
    backend.run_script(script, 1)
    assert backend.config.rng_seed_boundary == 'slippi-game-start'
    assert calls[0][calls[0].index('--rng-seed-boundary')+1] == 'slippi-game-start'
    assert calls[0][calls[0].index('--rng-seed')+1] == '33480'


def test_transport_uses_private_directories_and_clears_failed_state(configured, monkeypatch):
    backend, script = configured
    calls = []

    def emit(command, **kwargs):
        calls.append((command, kwargs))
        Path(command[command.index("--state-digest") + 1]).write_text(digest_row())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", emit)
    backend.run_script(script, 1)
    first_dir = backend.last_run_dir
    assert backend.observe().rng == 123
    backend.run_script(script, 1)
    assert backend.last_run_dir != first_dir
    command, options = calls[-1]
    assert "--vanilla-game" in command
    assert '--rng-seed-boundary' not in command
    assert command[command.index("--time-base") + 1] == "0"
    assert command[command.index("--card-dir") + 1].startswith(str(backend.last_run_dir))
    assert options["cwd"] == backend.last_run_dir
    assert options["timeout"] == 120
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 7))
    with pytest.raises(BackendError, match="exited 7"):
        backend.run_script(script, 1)
    with pytest.raises(BackendError, match="no successful"):
        backend.observe()
    assert (backend.last_run_dir / "host.log").is_file()


@pytest.mark.parametrize("mode", ["empty", "short", "timeout"])
def test_failed_transport_never_becomes_observations(configured, monkeypatch, mode):
    backend, script = configured

    def fail(command, **kwargs):
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        Path(command[command.index("--state-digest") + 1]).write_text("" if mode == "empty" else digest_row())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(BackendError):
        backend.run_script(script, 2)
    assert not backend.observations


@pytest.mark.parametrize("frames,timeout", [(0, 1), (-1, 1), (True, 1), (2**32, 1), (1, 0), (1, float("inf"))])
def test_invalid_run_limits(configured, frames, timeout):
    backend, script = configured
    with pytest.raises(BackendError):
        backend.run_script(script, frames, timeout)
    assert backend.last_run_dir is None


@pytest.mark.parametrize('stock', [False, True])
def test_batch_forwards_fixed_match(configured, monkeypatch, stock):
    from dataclasses import replace
    from yt2slp.match import MatchConfig, StockRules
    backend, script = configured
    backend.initialize(replace(backend.config, match=MatchConfig(stock_rules=StockRules() if stock else None)))
    def emit(command, **kwargs):
        assert command[command.index("--match") + 1] == "31 2 0 0 9 20 0 0 9"
        if stock:assert command[command.index('--stock-rules')+1]=='480 4'
        else:assert '--stock-rules' not in command
        Path(command[command.index("--state-digest") + 1]).write_text(digest_row())
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(subprocess, "run", emit)
    assert len(backend.run_script(script, 1)) == 1
