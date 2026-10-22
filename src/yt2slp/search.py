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


def run_schedule(backend: Backend, schedule: HorizontalSchedule, steps: int) -> tuple[Observation, ...]:
    initial = backend.observe()
    result = [initial]
    for step in range(steps):
        state = backend.step(schedule.pads(step))
        if state.match_frame != initial.match_frame + step + 1:
            raise ValueError("this controlled search requires one advancing match frame per VI; no offset guessed")
        result.append(state)
    return tuple(result)


def bounded_search(backend: Backend, samples: tuple[Sample, ...], candidates: tuple[HorizontalSchedule, ...],
                   steps: int, trials: Path) -> dict:
    if type(steps) is not int or not 1 <= steps <= 600:
        raise ValueError("one search window must contain 1..600 VI steps")
    if not candidates or len(candidates) > 128 or len(set(candidates)) != len(candidates):
        raise ValueError("supply 1..128 distinct candidate schedules")
    initial = backend.observe()
    if any(f < initial.match_frame or f > initial.match_frame + steps for s in samples for f in s.game_frames):
        raise ValueError("timeline lies outside this search window")
    trials.mkdir(exist_ok=False)
    checkpoint = backend.capture()
    results = []
    selected_trace = None
    selected_index = None
    for index, candidate in enumerate(candidates):
        backend.restore(checkpoint)
        trace = run_schedule(backend, candidate, steps)
        score = score_timeline(samples, trace)
        result = {"index": index, "schedule": asdict(candidate), "score": score}
        results.append(result)
        (trials / f"{index:03d}.json").write_text(json.dumps({**result, "states": [asdict(s) for s in trace]}, indent=2) + "\n")
        if score["accepted"] and selected_index is None:
            selected_index, selected_trace = index, trace
    accepted = [r["index"] for r in results if r["score"]["accepted"]]
    report = {"schema": 1, "kind": "bounded-horizontal-search", "window": [initial.match_frame, initial.match_frame + steps],
              "candidate_count": len(candidates), "total_candidate_vi_steps": len(candidates) * steps,
              "accepted_indices": accepted, "selected_index": selected_index, "candidates": results,
              "selection_policy": "first accepted in declared candidate order; retain all accepted alternatives",
              "original_inputs_identified": False, "global_search_exhausted": False,
              "declared_grid_exhausted": True, "selected_branch_rerun_matches": None,
              "passed": False, "checkpoint_portable": False}
    # Even on failure, remove the final rejected trial from the live branch.
    backend.restore(checkpoint)
    if selected_index is not None:
        replayed = run_schedule(backend, candidates[selected_index], steps)
        if replayed != selected_trace:
            raise ValueError("selected continuation did not repeat after restore")
        report["selected_schedule"] = asdict(candidates[selected_index])
        report["selected_branch_rerun_matches"] = True
        report["selected_score"] = score_timeline(samples, replayed)
        report["passed"] = report["selected_score"]["accepted"]
    return report
