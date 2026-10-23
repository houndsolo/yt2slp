"""Process-isolated native runs with cooperative VI stepping on a live game stack."""
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol
import csv
import json
import math
import os
import struct
import subprocess
import tempfile
import secrets
import re

from .evidence import Evidence, Provenance
from .match import MatchConfig, PadInput
from .native_control import ControlSession


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
    match: MatchConfig | None = None


@dataclass(frozen=True)
class RecordingStatus:
    """Last recorded post-frame and presence of a game-generated Game End event."""

    last_frame: int
    ended: bool


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

    def start(self, script: Path, timeout: float = 120, boot_limit: int = 6000) -> Observation:
        """Boot to a resumable boundary, or raise UnsupportedOperation."""
        ...

    def close(self) -> None:
        """Release any live session and reap its child process."""
        ...

    def step(self, inputs: tuple[PadInput, ...]) -> Observation:
        """Advance one documented backend boundary, or raise UnsupportedOperation."""
        ...

    def observe(self) -> Observation:
        """Return the latest selected state or raise BackendError if absent."""
        ...

    def capture(self) -> bytes:
        """Capture an opaque session-local checkpoint handle or fail explicitly."""
        ...

    def restore(self, checkpoint: bytes) -> None:
        """Restore a backend checkpoint or raise UnsupportedOperation."""
        ...

    def recording_status(self) -> RecordingStatus:
        """Return event-stream progress and genuine ending status, or fail explicitly."""
        ...

    def record(self, output: Path) -> None:
        """Write a selected simulation's replay or raise UnsupportedOperation."""
        ...


class NativeLinuxBackend:
    """Fresh-process batch runs and resumable VI-boundary sessions.

    start() boots with a script and pauses at the first live VS observation.
    step() supplies all four ports and advances one VI retrace, retaining the
    game stack. A retrace is not necessarily a completed match simulation frame.
    One reusable process checkpoint per session; in-memory recording follows restores.
    Use close() or a context manager to reap the process and frozen parent.
    """

    capabilities = {"run_script": True, "observe": True, "step": True, "fixed_match": True,
                    "capture": True, "restore": True, "record": True}

    def __init__(self) -> None:
        self._session: ControlSession | None = None
        self._checkpoint: tuple[bytes, tuple[Observation, ...]] | None = None
        self.config: RunConfig | None = None
        self.observations: tuple[Observation, ...] = ()
        self.last_run_dir: Path | None = None

    def initialize(self, config: RunConfig) -> None:
        """Bind validated paths; the child process loads/validates the game and ISO.

        Does not claim the ISO is authentic or the game booted. The native host
        verifies the retail DOL hash during run_script/start, without bypasses.
        """
        self.close()
        self.config = None
        self.observations = ()
        self.last_run_dir = None
        for label, path in (("headless host", config.host), ("game library", config.game_library), ("Melee NTSC 1.02 ISO", config.iso)):
            if not path.is_file():
                raise BackendError(f"missing {label}: {path}")
        if not os.access(config.host, os.X_OK):
            raise BackendError(f"headless host is not executable: {config.host}")
        if config.match is not None and not isinstance(config.match, MatchConfig):
            raise BackendError("match must be MatchConfig or None")
        if type(config.rng_seed) is not int or type(config.time_base) is not int:
            raise BackendError("rng_seed and time_base must be integers")
        if not 0 <= config.rng_seed <= 0xFFFFFFFF or not 0 <= config.time_base <= 0xFFFFFFFFFFFFFFFF:
            raise BackendError("rng_seed must be uint32 and time_base must be uint64")
        try:
            config.work_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=config.work_dir):
                pass
        except OSError as exc:
            raise BackendError(f"work directory is not writable: {exc}") from exc
        self.config = RunConfig(*(p.resolve() for p in (config.host, config.game_library, config.iso, config.work_dir)), config.rng_seed, config.time_base, config.match)

    def run_script(self, script: Path, retraces: int, timeout: float = 120) -> tuple[Observation, ...]:
        """Boot fresh and run a native script for exactly retraces VI boundaries.

        Preserves logs and partial digests in a unique work subdirectory, including
        failures. timeout is wall-clock seconds. This is not checkpoint stepping;
        the native host validates script syntax. Failure clears prior observations.
        """
        self.close()
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
        if c.match is not None:
            command += ["--match", c.match.native_argument()]
            if c.match.stock_rules is not None:
                command += ['--stock-rules', c.match.stock_rules.native_argument()]
        (run_dir / "config.json").write_text(json.dumps(asdict(c), default=str, indent=2) + "\n")
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

    def start(self, script: Path, timeout: float = 120, boot_limit: int = 6000) -> Observation:
        """Boot to a live VS retrace and wait there. timeout applies per response.

        The script navigates menus; the match override controls stage/players.
        After this returns, step inputs replace script input on all four ports.
        The initial snapshot may precede the match's GO animation completing.
        """
        self.close()
        self.observations = ()
        self.last_run_dir = None
        if self.config is None or self.config.match is None:
            raise BackendError("initialize with a fixed MatchConfig before start")
        if not math.isfinite(timeout) or timeout <= 0:
            raise BackendError("timeout must be finite and positive")
        if type(boot_limit) is not int or not 1 <= boot_limit <= 0xFFFFFFFF:
            raise BackendError("boot_limit must be an integer in 1..4294967295")
        if not script.is_file():
            raise BackendError(f"missing input script: {script}")
        c = self.config
        run_dir = Path(tempfile.mkdtemp(prefix="step-", dir=c.work_dir))
        self.last_run_dir = run_dir
        command = [str(c.host), "--iso", str(c.iso), "--game-library", str(c.game_library),
                   "--headless", "--fast", "--vanilla-game", "--no-gc-adapter",
                   "--rng-seed", str(c.rng_seed), "--time-base", str(c.time_base),
                   "--input-script", str(script.resolve()), "--card-dir", str(run_dir / "card"),
                   "--state-digest", str(run_dir / "state.csv"), "--match", c.match.native_argument(),
                   "--boot-limit", str(boot_limit)]
        if c.match.stock_rules is not None:
            command += ['--stock-rules', c.match.stock_rules.native_argument()]
        (run_dir / "config.json").write_text(json.dumps(asdict(c), default=str, indent=2) + "\n")
        try:
            self._session = ControlSession(command, run_dir, timeout)
            if self._session.receive() != "MUCONTROL 2":
                raise ValueError("unsupported native control protocol")
            state = self._receive_state()
            if not (state.scene_major == 2 and state.scene == 2 and state.match_frame > 0
                    and tuple(i for i, f in enumerate(state.fighters) if f[0]) == tuple(sorted(c.match.ports))):
                raise ValueError("native control did not pause in a live VS match")
            self.observations = (state,)
            return state
        except (OSError, ValueError) as exc:
            self._control_failure(exc)

    def _receive_state(self) -> Observation:
        assert self._session is not None
        line = self._session.receive()
        if not line.startswith("STATE "):
            raise ValueError("expected native STATE response")
        fields = line[6:].split(",")
        if len(fields) != 77 or any(not f.isascii() or not f.isdecimal() for f in fields):
            raise ValueError("invalid native state fields")
        values = tuple(map(int, fields))
        if any(v > 0xFFFFFFFF for v in values) or values[0] == 0:
            raise ValueError("invalid native state range")
        return Observation(*values[:5], tuple(values[i:i + 12] for i in range(5, 77, 12)))

    def _control_failure(self, exc: Exception) -> None:
        self.close()
        self.observations = ()
        raise BackendError(f"native control failed: {exc}; see {self.last_run_dir}/host.log") from exc

    def observe(self) -> Observation:
        """Read paused state without advancing; batch mode returns the final state."""
        if not self.observations:
            raise BackendError("no successful native run to observe")
        if self._session is not None:
            try:
                self._session.send("observe")
                if self._receive_state() != self.observations[-1]:
                    raise ValueError("native state changed while paused")
            except (OSError, ValueError) as exc:
                self._control_failure(exc)
        return self.observations[-1]

    def step(self, inputs: tuple[PadInput, ...]) -> Observation:
        """Resume to the next VI boundary, holding four raw PAD samples.

        No direct call to game.retrace or game.run is made here. Input reaches
        the game at its next ordinary PAD poll, not retroactively at this boundary.
        """
        if self._session is None:
            raise BackendError("start a native session before stepping")
        if not isinstance(inputs, (tuple, list)) or len(inputs) != 4 or any(not isinstance(p, PadInput) for p in inputs):
            raise BackendError("step requires exactly four PadInput values")
        command = "step " + " ".join(p.native_argument() for p in inputs)
        try:
            with (self.last_run_dir / "inputs.txt").open("a") as log:
                log.write(f"{self.observations[-1].retrace}: {command}\n")
            self._session.send(command)
            state = self._receive_state()
            if state.retrace != self.observations[-1].retrace + 1:
                raise ValueError("step did not advance exactly one VI retrace")
            self.observations += (state,)
            return state
        except (OSError, ValueError) as exc:
            self._control_failure(exc)

    def close(self) -> None:
        """Reap all branches and invalidate checkpoints; observations are historical."""
        self._checkpoint = None
        if self._session is not None:
            self._session.close()
            self._session = None

    def __enter__(self) -> "NativeLinuxBackend":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def capture(self) -> bytes:
        """Keep one frozen Linux process; return an opaque session-local handle.

        This is not serialized state. The handle cannot be used after close/start,
        with another backend instance, or in another Python process. The native
        guard requires a single-threaded live VS process. Memory cards are held
        in memory for the entire control session, including before capture.
        """
        if self._session is None:
            raise BackendError("start a native session before capture")
        if self._checkpoint is not None:
            raise UnsupportedOperation("one checkpoint per session; close/start to capture another")
        try:
            self._session.send("capture")
            response = self._session.receive()
            if response.startswith("UNSUPPORTED "):
                raise UnsupportedOperation(response[12:])
            if response != "CAPTURED" or self._receive_state() != self.observations[-1]:
                raise ValueError("capture did not preserve the paused state")
            handle = secrets.token_bytes(32)
            self._checkpoint = (handle, self.observations)
            self._checkpoint_event("capture")
            return handle
        except (OSError, ValueError) as exc:
            self._control_failure(exc)

    def restore(self, checkpoint: bytes) -> None:
        """Discard the running branch and fork again from the retained checkpoint.

        Restores process memory, native stack, host clocks/callbacks, inputs and
        in-memory card state. Diagnostic output is append-only and not rolled back.
        """
        if self._session is None:
            raise BackendError("start a native session before restore")
        if self._checkpoint is None or type(checkpoint) is not bytes or checkpoint != self._checkpoint[0]:
            raise BackendError("unknown or expired checkpoint handle for this session")
        try:
            self._session.send("restore")
            response = self._session.receive()
            if response != "RESTORED":
                raise ValueError(f"expected RESTORED, received {response}")
            state = self._receive_state()
            if state != self._checkpoint[1][-1]:
                raise ValueError("restored observation differs from captured state")
            self.observations = self._checkpoint[1]
            self._checkpoint_event("restore")
        except (OSError, ValueError) as exc:
            self._control_failure(exc)

    def _checkpoint_event(self, operation: str) -> None:
        with (self.last_run_dir / "inputs.txt").open("a") as log:
            log.write(f"{self.observations[-1].retrace}: {operation}\n")

    def recording_status(self) -> RecordingStatus:
        """Query the current branch without resuming, exporting, or inventing Game End."""
        if self._session is None:
            raise UnsupportedOperation("recording status requires a live control session")
        try:
            self._session.send("record-status")
            reply = self._session.receive()
            if reply.startswith("UNSUPPORTED "):
                raise UnsupportedOperation(reply[12:])
            match = re.fullmatch(r"RECORDING (-?[0-9]+) ([01])", reply)
            if match is None:
                raise ValueError("invalid recording status response")
            last_frame = int(match[1])
            if not -123 <= last_frame <= 0x7FFFFFFF:
                raise ValueError("invalid recording frame range")
            return RecordingStatus(last_frame, match[2] == "1")
        except (OSError, ValueError) as exc:
            self._control_failure(exc)

    def record(self, output: Path) -> None:
        """Export the current branch's real events, including its pre-checkpoint prefix.

        Does not advance or invent Game End. An unfinished match exports a partial
        replay. Explicit exports survive future restores and are never overwritten.
        """
        if self._session is None:
            raise UnsupportedOperation("record requires a live control session")
        if output.exists():
            raise BackendError(f"replay output already exists: {output}")
        try:
            self._session.send("record")
            reply = self._session.receive()
            if reply.startswith("UNSUPPORTED "):
                raise UnsupportedOperation(reply[12:])
            if not re.fullmatch(r"REPLAY [0-9]+", reply):
                raise ValueError("expected REPLAY size")
            size = int(reply[7:])
            if not 1 <= size <= 257 * 1024 * 1024:
                raise ValueError("invalid replay size")
            data = bytearray()
            while len(data) < size:
                chunk = self._session.receive()
                if not re.fullmatch(r"[0-9a-f]{2,2048}", chunk) or len(chunk) % 2:
                    raise ValueError("invalid replay chunk")
                data.extend(bytes.fromhex(chunk))
                if len(data) > size:
                    raise ValueError("replay exceeds declared size")
            if self._session.receive() != "RECORDED":
                raise ValueError("missing recording terminator")
        except (OSError, ValueError) as exc:
            self._control_failure(exc)
        # Publish only after the complete transport succeeds; exclusive creation.
        try:
            with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as handle:
                temporary = Path(handle.name)
                try:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                    os.link(temporary, output)  # atomic, refuses existing destinations
                finally:
                    temporary.unlink()
        except OSError as exc:
            raise BackendError(f"cannot write replay: {exc}") from exc
