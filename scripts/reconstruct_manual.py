"""One controlled search from manual video cues; no automatic vision/YouTube API.

The start recipe and finite input grid are explicit supplied hypotheses. A
passing sparse cue objective does not establish a matching pixel trajectory.
Run in Docker. All generated inputs, trials, reports and recordings stay local.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import time

from yt2slp.backend import NativeLinuxBackend, RunConfig
from yt2slp.match import MatchConfig, NEUTRAL_PADS, PlayerConfig
from yt2slp.search import bounded_search, run_schedule, schedule_from_dict
from yt2slp.timeline import load_timeline
from yt2slp.trajectory import native_identities, reproduce_prefix, render_interval, validate_prefix
from yt2slp.video import sha256


def advance_to(backend, frame):
    while backend.observe().match_frame < frame:
        previous = backend.observe().match_frame
        if backend.step(NEUTRAL_PADS).match_frame != previous + 1:
            raise ValueError("known neutral prefix did not advance one match frame per VI")
    if backend.observe().match_frame != frame:
        raise ValueError("requested checkpoint precedes actual match start")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True, help="ingested video directory")
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True, help="explicit known start and candidate grid JSON")
    parser.add_argument("--prefix", type=Path, help="sealed selected controller history for this continuation")
    args = parser.parse_args()
    video = json.loads((args.video / "video.json").read_text())
    samples = load_timeline(json.loads(args.timeline.read_text()), video)
    # Verify images still match the evidence bound by the manual timeline.
    for sample in samples:
        row = video["frames"][sample.video_frame]
        if sha256(args.video / row["image"]) != row["image_sha256"]:
            raise ValueError("annotated image has changed since ingestion")
    spec = json.loads(args.spec.read_text())
    if (spec.get("schema") != 1 or spec.get("case") != "fox-falco-battlefield-manual-v1"
            or not isinstance(spec.get("start_source"), str) or not spec["start_source"].strip()
            or spec.get("known_match") != {"stage": 31, "characters": [2, 20]}):
        raise ValueError("expected explicit supported start recipe and its source")
    frame, end = spec["checkpoint_frame"], spec["end_frame"]
    if type(frame) is not int or type(end) is not int or not 1 <= frame < end <= 1000:
        raise ValueError("invalid bounded match-frame window")
    if any(type(spec[k]) is not int or not 0 <= spec[k] <= 0xFFFFFFFFFFFFFFFF for k in ("rng_seed", "time_base")):
        raise ValueError("explicit integer seed/time base required")
    candidates = tuple(schedule_from_dict(c) for c in spec["candidates"])
    interval=render_interval(spec)
    config = RunConfig(Path("build/headless/melee_headless"), Path("build/game/melee_game.so"),
                       Path(os.environ.get("YT2SLP_ISO", "/assets/melee.iso")), Path(".local/runs"),
                       rng_seed=spec["rng_seed"], time_base=spec["time_base"],
                       match=MatchConfig(31, (PlayerConfig(2), PlayerConfig(20))))
    boot = Path("third_party/melee-unlocked/port/scripts/native_vs.txt")
    prefix=json.loads(args.prefix.read_text()) if args.prefix else None
    if spec.get('required_prefix_sha256') and (not args.prefix or sha256(args.prefix)!=spec['required_prefix_sha256']):
        raise ValueError('required selected prefix is missing or changed')
    if prefix is not None:
        validate_prefix(prefix,spec,video['source_sha256'],native_identities(config,boot))
        spec['required_prefix_sha256']=sha256(args.prefix)
    started = time.monotonic()
    with NativeLinuxBackend() as backend:
        backend.initialize(config)
        initial = backend.start(boot, timeout=180)
        root = backend.last_run_dir
        if prefix is None:
            advance_to(backend, frame)
        else:
            (root/'prefix.json').write_text(args.prefix.read_text())
            reproduce_prefix(backend,prefix,root/'prefix-reproduced.slp')
        (root / "timeline.json").write_text(args.timeline.read_text())
        (root / "search-spec.json").write_text(json.dumps(spec,indent=2)+'\n')
        report = bounded_search(backend, samples, candidates, end - frame, root / "trials")
        report.update(case=spec["case"], initial_match_frame=initial.match_frame, elapsed_seconds=time.monotonic() - started,
                      start_source=spec["start_source"], source_video_sha256=video["source_sha256"],
                      identities={str(p): sha256(p) for p in (args.timeline, args.spec, args.video / "video.json",
                          config.host, config.game_library, config.iso, boot, Path(__file__), Path("src/yt2slp/search.py"),
                          Path("src/yt2slp/timeline.py"), Path("src/yt2slp/video.py"), Path("uv.lock"))},
                      git_head=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                      engine_head=subprocess.check_output(["git", "-C", "third_party/melee-unlocked", "rev-parse", "HEAD"], text=True).strip(),
                      parser_validated=False, official_playback_validated=False, pixel_agreement_measured=False,
                      search_resumable_across_sessions=False)
        report.update(render_interval=interval,native_identities=native_identities(config,boot),
            prefix_reproduction_passed=True if prefix else None,
            prefix_replay_sha256=prefix['replay_sha256'] if prefix else None,
            trajectory_segments=prefix['segments'].copy() if prefix else [])
        if args.prefix:
            report['identities'][str(root/'prefix.json')]=sha256(root/'prefix.json')
        report['identities'][str(Path('src/yt2slp/trajectory.py'))]=sha256(Path('src/yt2slp/trajectory.py'))
        if report["passed"]:
            status = backend.recording_status()
            if status.last_frame != end or status.ended:
                raise ValueError("unexpected partial recording boundary")
            backend.record(root / "selected.slp")
            selected = backend.observations
            (root / "selected-observations.json").write_text(json.dumps([asdict(s) for s in selected]) + "\n")
            report['selected_observations_sha256']=sha256(root/'selected-observations.json')
            report['trajectory_segments'].append({'first':frame,'last':end,'schedule':report['selected_schedule']})
            # Fresh boot with only the chosen inputs checks trial events cannot leak.
            with NativeLinuxBackend() as fresh:
                fresh.initialize(config)
                fresh.start(boot, timeout=180)
                if prefix is None:
                    advance_to(fresh, frame)
                else:
                    reproduce_prefix(fresh,prefix,root/'fresh-prefix-reproduced.slp')
                run_schedule(fresh, schedule_from_dict(report["selected_schedule"]), end - frame)
                fresh.record(root / "fresh-selected.slp")
                report["fresh_selected_observations_match"] = fresh.observations == selected
                report["fresh_recording_bytes_match"] = sha256(root / "selected.slp") == sha256(root / "fresh-selected.slp")
                report["fresh_run"] = str(fresh.last_run_dir)
            with (root / "parser-result.json").open("x") as handle:
                subprocess.run(["node", "tools/slippi-parser/validate.cjs", str(root / "selected.slp"),
                                "--last-frame", str(end)], stdout=handle, check=True)
            report["parser_validated"] = True
            report["selected_replay_sha256"] = sha256(root / "selected.slp")
            report["passed"] &= report["fresh_selected_observations_match"] and report["fresh_recording_bytes_match"]
        (root / "search-result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"run": str(root), **{k: report[k] for k in ("passed", "candidate_count", "accepted_indices", "selected_index")}}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
