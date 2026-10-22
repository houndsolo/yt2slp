"""Backend contract and a process-isolated adapter for MU's bounded Linux runner.

The native ABI uses fixed low addresses and owns a blocking game loop. Loading it
into Python with ctypes is not a safe stepping API. Each run below gets a fresh
process and private card directory; unsupported interactive operations fail.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import csv
import math
import os
import struct
import subprocess
import tempfile

from .evidence import Evidence, Provenance


class BackendError(RuntimeError):
    """A missing prerequisite, failed native run, or invalid native output."""


class UnsupportedOperation(BackendError):
    """The selected backend has no verified implementation of this operation."""


@dataclass(frozen=True)
class RunConfig:
    """Explicit local artifacts and deterministic boot inputs for a bounded run."""

    host: Path
    game_library: Path
    iso: Path
    work_dir: Path
    rng_seed: int = 1
    time_base: int = 0


@dataclass(frozen=True)
class Observation:
    """Selected MuStatePod fields at a retrace, not a complete savestate.

    Float fields retain their uint32 IEEE-754 bits exactly as MU emits them.
    Retraces include menus; match_frame is a separate game counter.
    """

    retrace: int
    scene_major: int
    scene: int
    match_frame: int
    rng: int
    fighters: tuple[tuple[int, ...], ...]

    def as_evidence(self) -> Evidence["Observation"]:
        """Label simulated state as inferred relative to the original video."""
        return Evidence(self, Provenance.INFERRED, "melee-unlocked:MuStatePod/retrace")


def decode_float_bits(value: int) -> float:
    """Decode a uint32 field for display only; preserve raw bits for comparisons."""
    return struct.unpack("!f", struct.pack("!I", value))[0]


def read_observations(path: Path) -> tuple[Observation, ...]:
    """Read MU's 77-column digest, rejecting malformed or unordered uint32 rows.

    Raises BackendError for missing, empty, truncated, or invalid output.
    """
    result = []
    try:
        with path.open(newline="") as handle:
            for line, row in enumerate(csv.reader(handle), 1):
                if len(row) != 77:
                    raise ValueError(f"line {line}: expected 77 columns, got {len(row)}")
                values = tuple(int(value) for value in row)
                if any(value < 0 or value > 0xFFFFFFFF for value in values):
                    raise ValueError(f"line {line}: field outside uint32")
                if values[0] != len(result) + 1:
                    raise ValueError(f"line {line}: retraces must start at 1 and be contiguous")
                result.append(Observation(*values[:5], tuple(values[i:i + 12] for i in range(5, 77, 12))))
    except (OSError, ValueError) as exc:
        raise BackendError(f"invalid state digest: {exc}") from exc
    if not result:
        raise BackendError("native run emitted no observations")
    return tuple(result)


class Backend(Protocol):
    """Common contract; capability errors are part of this interface.

    initialize binds configuration; it need not start a game. Implementations
    must describe whether step is resumable and what a checkpoint covers.
    """

    def initialize(self, config: RunConfig) -> None:
        """Validate and bind artifacts, raising BackendError on missing inputs."""
        ...

    def step(self, inputs: object) -> Observation:
        """Advance one simulation frame, or raise UnsupportedOperation."""
        ...

    def observe(self) -> Observation:
        """Return the latest selected state or raise BackendError if absent."""
        ...

    def capture(self) -> bytes:
        """Capture a restorable checkpoint or raise UnsupportedOperation."""
        ...

    def restore(self, checkpoint: bytes) -> None:
        """Restore a backend checkpoint or raise UnsupportedOperation."""
        ...

    def record(self, output: Path) -> None:
        """Write a selected simulation's replay or raise UnsupportedOperation."""
        ...


class NativeLinuxBackend:
    """Bounded fresh-process runs; no interactive stepping, restore, or recording.

    Supported native CLI operations are compiled/tested independently. Actual
    game startup and these batch runs require a user-provided retail ISO.
    """

    capabilities = {"run_script": True, "observe": True, "step": False,
                    "capture": False, "restore": False, "record": False}

    def __init__(self) -> None:
        self.config: RunConfig | None = None
        self.observations: tuple[Observation, ...] = ()
        self.last_run_dir: Path | None = None

    def initialize(self, config: RunConfig) -> None:
        """Bind validated paths; the child process loads/validates the game and ISO.

        Does not claim the ISO is authentic or the game booted. The native host
        verifies the retail DOL hash during run_script, without bypasses.
        """
        self.config = None
        self.observations = ()
        self.last_run_dir = None
        for label, path in (("headless host", config.host), ("game library", config.game_library), ("Melee NTSC 1.02 ISO", config.iso)):
            if not path.is_file():
                raise BackendError(f"missing {label}: {path}")
        if not os.access(config.host, os.X_OK):
            raise BackendError(f"headless host is not executable: {config.host}")
        if not 0 <= config.rng_seed <= 0xFFFFFFFF or not 0 <= config.time_base <= 0xFFFFFFFFFFFFFFFF:
            raise BackendError("rng_seed must be uint32 and time_base must be uint64")
        try:
            config.work_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=config.work_dir):
                pass
        except OSError as exc:
            raise BackendError(f"work directory is not writable: {exc}") from exc
        self.config = RunConfig(*(p.resolve() for p in (config.host, config.game_library, config.iso, config.work_dir)), config.rng_seed, config.time_base)

    def run_script(self, script: Path, retraces: int, timeout: float = 120) -> tuple[Observation, ...]:
        """Boot fresh and run a native script for exactly retraces VI boundaries.

        Preserves logs and partial digests in a unique work subdirectory, including
        failures. timeout is wall-clock seconds. This is not checkpoint stepping;
        the native host validates script syntax. Failure clears prior observations.
        """
        self.observations = ()
        self.last_run_dir = None
        if self.config is None:
            raise BackendError("initialize the backend before running a script")
        if type(retraces) is not int or not 1 <= retraces <= 0xFFFFFFFF:
            raise BackendError("retraces must be an integer in 1..4294967295")
        if not math.isfinite(timeout) or timeout <= 0:
            raise BackendError("timeout must be finite and positive")
        if not script.is_file():
            raise BackendError(f"missing input script: {script}")
        c = self.config
        run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=c.work_dir))
        self.last_run_dir = run_dir
        digest = run_dir / "state.csv"
        command = [str(c.host), "--iso", str(c.iso), "--game-library", str(c.game_library),
                   "--headless", "--fast", "--vanilla-game", "--no-gc-adapter",
                   "--rng-seed", str(c.rng_seed), "--time-base", str(c.time_base),
                   "--frames", str(retraces), "--input-script", str(script.resolve()),
                   "--card-dir", str(run_dir / "card"), "--state-digest", str(digest)]
        try:
            with (run_dir / "host.log").open("w") as log:
                completed = subprocess.run(command, cwd=run_dir, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise BackendError(f"native run timed out; see {run_dir / 'host.log'}") from exc
        except OSError as exc:
            raise BackendError(f"cannot run native host: {exc}") from exc
        if completed.returncode:
            raise BackendError(f"native host exited {completed.returncode}; see {run_dir / 'host.log'}")
        observations = read_observations(digest)
        if len(observations) != retraces:
            raise BackendError(f"native host produced {len(observations)} of {retraces} requested retraces")
        self.observations = observations
        return observations

    def observe(self) -> Observation:
        """Return the last successful run's final state; no fabricated zero state."""
        if not self.observations:
            raise BackendError("no successful native run to observe")
        return self.observations[-1]

    def step(self, inputs: object) -> Observation:
        """Fail: game.run owns the stack; retrace is not a one-frame step API."""
        raise UnsupportedOperation("step: no resumable frame-boundary protocol; use run_script for a fresh bounded run")

    def capture(self) -> bytes:
        """Fail: MuStatePod is an observation, not a complete checkpoint."""
        raise UnsupportedOperation("capture: Linux host does not integrate game and host checkpoint state")

    def restore(self, checkpoint: bytes) -> None:
        """Fail until stack, host timing, memory and recording transactions exist."""
        raise UnsupportedOperation("restore: no safe game checkpoint boundary is exposed")

    def record(self, output: Path) -> None:
        """Fail: this host has no replay_event sink; never create a dummy .slp."""
        raise UnsupportedOperation("record: minimal Linux host has no replay event sink; full source host integration is required")
