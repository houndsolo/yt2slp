"""Manually sourced visual cues, separated from simulation-only hidden state.

This first objective uses coarse categorical cues, not pixel/world coordinates.
Its explicit frame uncertainty is a set of alternative native frame keys. All
cues from one video sample must fit the same key; offsets are never fitted.
"""
from dataclasses import dataclass
from copy import deepcopy
from fractions import Fraction
import math

from .backend import Observation, decode_float_bits
from .evidence import Evidence, Provenance
from .timer_labels import summarize_labels

# Retail common action IDs from the pinned engine ftCommon/forward.h.
ACTION_GROUPS = {"idle": {14}, "ground_locomotion": {15, 16, 17, 20, 21, 22, 23},
                 "airborne": set(range(25, 39))}
FIELDS = {"action_group", "facing", "damage", "horizontal_order"}


@dataclass(frozen=True)
class Cue:
    player: int
    field: str
    evidence: Evidence


@dataclass(frozen=True)
class Sample:
    video_frame: int
    game_frames: tuple[int, ...]
    alignment: Evidence
    cues: tuple[Cue, ...]
    frame_clock: str = 'native-match'


def evidence(raw: dict) -> Evidence:
    return Evidence(raw["value"], Provenance(raw["provenance"]), raw["source"])


def load_timeline(document: dict, video: dict) -> tuple[Sample, ...]:
    if (document.get("schema") != 1 or document.get("kind") != "manual-visual-cues"
            or video.get("schema") != 1 or video.get("kind") != "local-video"
            or document.get("video_sha256") != video.get("source_sha256")):
        raise ValueError("unsupported timeline or video identity mismatch")
    clock=document.get('frame_clock','native-match')
    if clock not in ('native-match','slippi-replay'):raise ValueError('unsupported timeline frame clock')
    result = []
    for raw in document["samples"]:
        index = raw["video_frame"]
        if (type(index) is not int or not 0 <= index < len(video["frames"])
                or (result and index <= result[-1].video_frame)):
            raise ValueError("video sample indices must be unique and increasing")
        if raw["image_sha256"] != video["frames"][index]["image_sha256"]:
            raise ValueError("manual annotation image identity mismatch")
        alignment = evidence(raw["alignment"])
        candidates = alignment.value
        if (not isinstance(candidates, list) or not candidates or len(candidates) > 9
                or any(type(f) is not int or f < (-123 if clock=='slippi-replay' else 1) for f in candidates)
                or candidates != sorted(set(candidates))):
            raise ValueError("alignment requires 1..9 explicit increasing game-frame candidates")
        if result and candidates[0] <= result[-1].game_frames[-1]:
            raise ValueError("alignment windows must be increasing and non-overlapping")
        cues = []
        for item in raw["cues"]:
            player, field = item["player"], item["field"]
            if type(player) is not int or player not in (0, 1) or field not in FIELDS:
                raise ValueError("unsupported cue player/field")
            if any(c.player == player and c.field == field for c in cues):
                raise ValueError("duplicate cue for player/field")
            item_evidence = evidence(item["evidence"])
            values = item_evidence.value
            if values is not None:
                if not isinstance(values, list) or not values:
                    raise ValueError("known cues require a nonempty list of alternatives")
                valid = {"action_group": set(ACTION_GROUPS), "facing": {"left", "right"},
                         "horizontal_order": {"left", "right"}}.get(field)
                if field == "damage":
                    if any(type(v) is not int or not 0 <= v <= 999 for v in values):
                        raise ValueError("damage alternatives must be displayed integers in 0..999")
                elif any(type(v) is not str or v not in valid for v in values):
                    raise ValueError("unsupported categorical cue")
            cues.append(Cue(player, field, item_evidence))
        result.append(Sample(index, tuple(candidates), alignment, tuple(cues),clock))
    if not result or not any(c.evidence.value is not None for s in result for c in s.cues):
        raise ValueError("timeline needs at least one known visual cue")
    return tuple(result)


def predicted_cue(state: Observation, cue: Cue, player_ports=(0,1)):
    if state.scene_major != 2 or state.scene != 2:
        raise ValueError("simulation left supported VS scene")
    fighter = state.fighters[player_ports[cue.player]]
    if len(fighter) != 12 or not fighter[0]:
        raise ValueError("missing simulated fighter")
    if cue.field == "action_group":
        return next((name for name, ids in ACTION_GROUPS.items() if fighter[2] in ids), "other")
    if cue.field == "horizontal_order":
        other = state.fighters[player_ports[1 - cue.player]]
        if len(other) != 12 or not other[0]:
            raise ValueError("missing other simulated fighter")
        x, other_x = decode_float_bits(fighter[4]), decode_float_bits(other[4])
        if not math.isfinite(x) or not math.isfinite(other_x):
            raise ValueError("non-finite simulated coordinate")
        return "right" if x > other_x else "left" if x < other_x else "overlap"
    value = decode_float_bits(fighter[11 if cue.field == "facing" else 10])
    if not math.isfinite(value):
        raise ValueError("non-finite simulated cue")
    if cue.field == "facing":
        return "right" if value > 0 else "left" if value < 0 else "unknown"
    # The damage HUD displays integer damage; fractional simulated damage stays hidden.
    return max(0, min(999, math.floor(value)))


def score_timeline(samples: tuple[Sample, ...], states: tuple[Observation, ...], *,
                   player_ports=(0,1),frame_keys=None) -> dict:
    if (type(player_ports) is not tuple or len(player_ports)!=2
            or any(type(p) is not int or not 0<=p<=3 for p in player_ports) or len(set(player_ports))!=2):
        raise ValueError('two distinct physical player ports are required')
    clock='native-match' if frame_keys is None else 'slippi-replay'
    if any(s.frame_clock!=clock for s in samples):raise ValueError('timeline and simulation frame clocks differ')
    keys=tuple(s.match_frame for s in states) if frame_keys is None else tuple(frame_keys)
    if len(keys)!=len(states) or any(type(k) is not int for k in keys):
        raise ValueError('every observation requires its own explicit frame key')
    indexed = {}
    for key,state in zip(keys,states):
        if key in indexed:
            raise ValueError("duplicate match-frame boundaries are unsupported in this controlled case")
        indexed[key] = state
    results = []
    for sample in samples:
        missing = sorted(set(sample.game_frames) - indexed.keys())
        if missing:
            # Missing coverage cannot be rewarded by choosing a better-covered offset.
            raise ValueError(f"missing candidate simulation frames: {missing}")
        possibilities = []
        for frame in sample.game_frames:
            checks = [{"player": c.player, "field": c.field, "expected": c.evidence.value,
                       "predicted": predicted_cue(indexed[frame], c,player_ports)}
                      for c in sample.cues if c.evidence.value is not None]
            for check in checks:
                check["matched"] = check["predicted"] in check["expected"]
            possibilities.append({"frame": frame, "violations": sum(not c["matched"] for c in checks),
                                  "checks": checks})
        best = min(p["violations"] for p in possibilities)
        results.append({"video_frame": sample.video_frame, "violations": best,
                        "equally_best_frames": [p["frame"] for p in possibilities if p["violations"] == best],
                        "possibilities": possibilities})
    count = sum(c.evidence.value is not None for s in samples for c in s.cues)
    violations = sum(r["violations"] for r in results)
    return {"violations": violations, "known_cues": count,
            "unknown_cues": sum(c.evidence.value is None for s in samples for c in s.cues),
            "accepted": count > 0 and violations == 0, "samples": results,
            "policy": "all known categorical cues must match; uniform unit cost per violation; no fitted offset",
            "pixel_or_world_position_error_measured": False}


def apply_manual_timer_labels(automatic: dict, annotations: dict, video: dict,
                             timers: dict, first: int, last: int) -> dict:
    """Fill unread timers with individually sourced manual readings; retain failures."""
    if (annotations.get("schema") != 1 or annotations.get("kind") != "manual-timer-labels"
            or annotations.get("video_sha256") != video["source_sha256"]):
        raise ValueError("manual timer annotation video identity mismatch")
    mapping = {timer: int(frame) for frame, timer in timers.items()}
    if len(mapping) != len(timers):
        raise ValueError("ambiguous timer mapping")
    result = deepcopy(automatic)
    indexed = {r["video_frame"]: r for r in result["records"]}
    seen = set()
    for entry in annotations["labels"]:
        index = entry["video_frame"]
        if type(index) is not int or index not in indexed or index in seen:
            raise ValueError("invalid/duplicate manual timer image index")
        seen.add(index)
        if entry["image_sha256"] != video["frames"][index]["image_sha256"]:
            raise ValueError("manual timer image identity mismatch")
        reading = evidence(entry["evidence"])
        if reading.provenance != Provenance.OBSERVED or not isinstance(reading.value, str) or reading.value not in mapping:
            raise ValueError("manual timer needs an observed, supported exact timer string")
        row, frame = indexed[index], mapping[reading.value]
        if row["frame"] is not None and row["frame"] != frame:
            raise ValueError("manual timer contradicts an automatic label; review calibration separately")
        row.update(automatic_frame=row["frame"], frame=frame, manual_timer=reading.value,
                   manual_source=reading.source, frame_label_provenance="inferred from individually observed manual timer")
    result.update(summarize_labels(result["records"], first, last))
    result["manual_label_count"] = len(seen)
    result["automatic_coverage_passed"] = automatic["passed"]
    result["method"] += "; unread timers may have explicit, identity-bound manual readings"
    return result


def check_rendered_clock_timing(labels: dict, video: dict) -> dict:
    """Check this unpaused 60 Hz fixture against PTS without fitting a time scale."""
    records = [r for r in labels["records"] if r["frame"] in labels["selected"]]
    base = Fraction(video["time_base"])
    if not records:
        raise ValueError("no timed source images")
    first = records[0]
    origin = video["frames"][first["video_frame"]]["pts"]
    errors = [abs((video["frames"][r["video_frame"]]["pts"] - origin) * base
                  - Fraction(r["frame"] - first["frame"], 60)) for r in records]
    return {"passed": all(error <= base for error in errors), "max_error_seconds": str(max(errors)),
            "tolerance_seconds": str(base), "policy": "unpaused 60 Hz game clock; allow one source time-base tick; no scale fit"}
