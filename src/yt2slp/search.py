"""Bounded, one-window controller search using the session's single checkpoint.

Candidates are explicit hypotheses. No reference replay/input/state is read.
The active branch is restored and rerun before it can be exported by the caller.
"""
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .backend import Backend, Observation
from .match import NEUTRAL_PADS, PadInput
from .timeline import Sample, score_timeline


@dataclass(frozen=True)
class HorizontalSchedule:
    """P1 neutral for start_after retraces, then a constant raw horizontal axis."""
    start_after: int
    stick_x: int

    def __post_init__(self):
        if type(self.start_after) is not int or not 0 <= self.start_after <= 600:
            raise ValueError("start_after must be in 0..600")
        PadInput(stick_x=self.stick_x)

    def pads(self, step: int):
        return (PadInput(stick_x=self.stick_x), *NEUTRAL_PADS[1:]) if step >= self.start_after else NEUTRAL_PADS


@dataclass(frozen=True)
class HorizontalSequence:
    """Ordered P1 axis changes at zero-based VI request indices; neutral before the first."""
    phases: tuple[HorizontalSchedule, ...]

    def __post_init__(self):
        if (type(self.phases) is not tuple or not 1 <= len(self.phases) <= 16
                or any(not isinstance(p, HorizontalSchedule) for p in self.phases)):
            raise ValueError("supply a tuple of 1..16 horizontal phases")
        for previous, current in zip(self.phases, self.phases[1:]):
            if current.start_after <= previous.start_after or current.stick_x == previous.stick_x:
                raise ValueError("phases must advance strictly and change the held axis")

    def pads(self, step: int):
        for phase in reversed(self.phases):
            if step >= phase.start_after:
                return phase.pads(step)
        return NEUTRAL_PADS


@dataclass(frozen=True)
class PadPhase:
    """Complete P1 main-stick/button sample at a VI request index; no inherited buttons."""
    start_after: int
    stick_x: int
    stick_y: int
    button: int

    def __post_init__(self):
        if type(self.start_after) is not int or not 0 <= self.start_after <= 600:
            raise ValueError("start_after must be in 0..600")
        PadInput(stick_x=self.stick_x, stick_y=self.stick_y, button=self.button)
        if self.button & 0x1000:
            raise ValueError("Start/pause is outside the unpaused search contract")

    def pads(self, step: int):
        return ((PadInput(stick_x=self.stick_x, stick_y=self.stick_y, button=self.button), *NEUTRAL_PADS[1:])
                if step >= self.start_after else NEUTRAL_PADS)


@dataclass(frozen=True)
class PadSequence:
    phases: tuple[PadPhase, ...]

    def __post_init__(self):
        if (type(self.phases) is not tuple or not 1 <= len(self.phases) <= 16
                or any(not isinstance(p, PadPhase) for p in self.phases)):
            raise ValueError("supply a tuple of 1..16 controller phases")
        for previous, current in zip(self.phases, self.phases[1:]):
            if (current.start_after <= previous.start_after
                    or (current.stick_x, current.stick_y, current.button)
                    == (previous.stick_x, previous.stick_y, previous.button)):
                raise ValueError("phases must advance strictly and change the held controller sample")

    def pads(self, step: int):
        for phase in reversed(self.phases):
            if step >= phase.start_after:
                return phase.pads(step)
        return NEUTRAL_PADS


@dataclass(frozen=True)
class PortProgram:
    port: int
    program: PadSequence

    def __post_init__(self):
        if type(self.port) is not int or not 0<=self.port<=3 or not isinstance(self.program,PadSequence):
            raise ValueError('port program requires a physical port and controller phases')


@dataclass(frozen=True)
class TwoPlayerSequence:
    port_programs: tuple[PortProgram,PortProgram]

    def __post_init__(self):
        if (type(self.port_programs) is not tuple or len(self.port_programs)!=2
                or any(not isinstance(p,PortProgram) for p in self.port_programs)
                or self.port_programs[0].port==self.port_programs[1].port):
            raise ValueError('two distinct physical controller programs are required')

    def pads(self,step):
        result=[PadInput(err=-1) for _ in range(4)]
        for player in self.port_programs:result[player.port]=player.program.pads(step)[0]
        return tuple(result)


ControllerSchedule = HorizontalSchedule | HorizontalSequence | PadSequence | TwoPlayerSequence


def schedule_from_dict(document: dict) -> ControllerSchedule:
    """Read legacy horizontal formats or explicit main-stick/button snapshots."""
    if not isinstance(document, dict):
        raise ValueError("candidate schedule must be an object")
    if set(document) == {"start_after", "stick_x"}:
        return HorizontalSchedule(**document)
    if set(document) == {"phases"} and type(document["phases"]) is list:
        phases = document["phases"]
        if any(not isinstance(p, dict) or set(p) != {"start_after", "stick_x"} for p in phases):
            raise ValueError("each phase requires start_after and stick_x only")
        return HorizontalSequence(tuple(HorizontalSchedule(**p) for p in phases))
    if set(document) == {"pad_phases"} and type(document["pad_phases"]) is list:
        phases = document["pad_phases"]
        if any(not isinstance(p, dict) or set(p) != {"start_after", "stick_x", "stick_y", "button"} for p in phases):
            raise ValueError("controller phases require explicit start_after, stick_x, stick_y and button only")
        return PadSequence(tuple(PadPhase(**p) for p in phases))
    if set(document)=={'port_programs'} and type(document['port_programs']) is list:
        programs=[]
        for player in document['port_programs']:
            if not isinstance(player,dict) or set(player)!={'port','pad_phases'}:
                raise ValueError('each player program requires port and pad_phases only')
            programs.append(PortProgram(player['port'],schedule_from_dict({'pad_phases':player['pad_phases']})))
        return TwoPlayerSequence(tuple(programs))
    raise ValueError("unsupported candidate schedule format")


def schedule_document(schedule: ControllerSchedule) -> dict:
    if isinstance(schedule,TwoPlayerSequence):
        return {'port_programs':[{'port':p.port,**schedule_document(p.program)} for p in schedule.port_programs]}
    if isinstance(schedule, PadSequence):
        return {"pad_phases": [asdict(p) for p in schedule.phases]}
    if isinstance(schedule, HorizontalSequence):
        return {"phases": [asdict(p) for p in schedule.phases]}
    return asdict(schedule)


def run_schedule(backend: Backend, schedule: ControllerSchedule, steps: int) -> tuple[Observation, ...]:
    initial = backend.observe()
    result = [initial]
    for step in range(steps):
        state = backend.step(schedule.pads(step))
        if state.match_frame != initial.match_frame + step + 1:
            raise ValueError("this controlled search requires one advancing match frame per VI; no offset guessed")
        result.append(state)
    return tuple(result)


def run_recorded_schedule(backend, schedule, steps):
    """Keep raw observations and separately query signed game-generated replay keys."""
    states=[backend.observe()];keys=[backend.recording_status().last_frame]
    for index in range(steps):
        states.append(backend.step(schedule.pads(index)))
        key=backend.recording_status().last_frame
        if key!=keys[-1]+1:raise ValueError('recorded frame did not advance one per VI; no frame mapping guessed')
        keys.append(key)
    return tuple(states),tuple(keys)


def bounded_search(backend: Backend, samples: tuple[Sample, ...], candidates: tuple[ControllerSchedule, ...],
                   steps: int, trials: Path, *, frame_clock='native-match',player_ports=(0,1)) -> dict:
    if type(steps) is not int or not 1 <= steps <= 600:
        raise ValueError("one search window must contain 1..600 VI steps")
    if not candidates or len(candidates) > 128 or len(set(candidates)) != len(candidates):
        raise ValueError("supply 1..128 distinct candidate schedules")
    if any(isinstance(c, (HorizontalSequence, PadSequence)) and c.phases[-1].start_after >= steps for c in candidates):
        raise ValueError("every declared phase must occur inside the search window")
    for candidate in candidates:
        if isinstance(candidate,TwoPlayerSequence):
            if tuple(p.port for p in candidate.port_programs)!=player_ports:
                raise ValueError('controller programs differ from the declared player-port order')
            if any(p.program.phases[-1].start_after>=steps for p in candidate.port_programs):
                raise ValueError('every player phase must occur inside the window')
        elif player_ports!=(0,1):raise ValueError('legacy schedules control the default ports only')
    if frame_clock not in ('native-match','slippi-replay') or any(s.frame_clock!=frame_clock for s in samples):
        raise ValueError('timeline and search frame clocks differ')
    initial = backend.observe()
    first=initial.match_frame if frame_clock=='native-match' else backend.recording_status().last_frame
    if any(f < first or f > first + steps for s in samples for f in s.game_frames):
        raise ValueError("timeline lies outside this search window")
    def run(candidate):
        return ((run_schedule(backend,candidate,steps),None) if frame_clock=='native-match'
                else run_recorded_schedule(backend,candidate,steps))
    def score(trace,keys):return score_timeline(samples,trace,frame_keys=keys,player_ports=player_ports)
    trials.mkdir(exist_ok=False)
    checkpoint = backend.capture()
    results = []
    selected_trace = None
    selected_index = None
    selected_keys = None
    for index, candidate in enumerate(candidates):
        backend.restore(checkpoint)
        trace,keys = run(candidate)
        cost = score(trace,keys)
        result = {"index": index, "schedule": schedule_document(candidate), "score": cost}
        results.append(result)
        (trials / f"{index:03d}.json").write_text(json.dumps({**result, "states": [asdict(s) for s in trace],
            **({'replay_frame_keys':keys} if keys is not None else {})}, indent=2) + "\n")
        if cost["accepted"] and selected_index is None:
            selected_index, selected_trace, selected_keys = index, trace,keys
    accepted = [r["index"] for r in results if r["score"]["accepted"]]
    kind = "bounded-controller-search" if any(isinstance(c, (PadSequence,TwoPlayerSequence)) for c in candidates) else "bounded-horizontal-search"
    report = {"schema": 1, "kind": kind, "window": [first, first + steps],
              "candidate_count": len(candidates), "total_candidate_vi_steps": len(candidates) * steps,
              "accepted_indices": accepted, "selected_index": selected_index, "candidates": results,
              "selection_policy": "first accepted in declared candidate order; retain all accepted alternatives",
              "original_inputs_identified": False, "global_search_exhausted": False,
              "declared_grid_exhausted": True, "selected_branch_rerun_matches": None,
              "passed": False, "checkpoint_portable": False}
    if frame_clock!='native-match' or player_ports!=(0,1):
        report.update(frame_clock=frame_clock,player_ports=player_ports)
    # Even on failure, remove the final rejected trial from the live branch.
    backend.restore(checkpoint)
    if selected_index is not None:
        replayed,keys = run(candidates[selected_index])
        if replayed != selected_trace or keys!=selected_keys:
            raise ValueError("selected continuation did not repeat after restore")
        report["selected_schedule"] = schedule_document(candidates[selected_index])
        report["selected_branch_rerun_matches"] = True
        report["selected_score"] = score(replayed,keys)
        report["passed"] = report["selected_score"]["accepted"]
    return report
