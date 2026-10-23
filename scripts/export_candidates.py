"""Export genuine replays for every coarse-accepted candidate, in Docker."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess

from yt2slp.backend import NativeLinuxBackend, RunConfig
from yt2slp.match import MatchConfig
from yt2slp.search import run_schedule, schedule_from_dict
from yt2slp.timeline import load_timeline, score_timeline
from yt2slp.video import sha256
from yt2slp.trajectory import native_identities, reproduce_prefix, render_interval, validate_prefix
from reconstruct_manual import advance_to


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-candidates", type=int, default=8)
    args = parser.parse_args()
    root = args.search.resolve()
    prior = json.loads((root / "search-result.json").read_text())
    spec = json.loads((root / "search-spec.json").read_text())
    video = json.loads((args.video / "video.json").read_text())
    timeline = json.loads((root / "timeline.json").read_text())
    samples = load_timeline(timeline, video)
    indices = prior["accepted_indices"]
    if (not prior["passed"] or not prior["declared_grid_exhausted"]
            or not 1 <= args.max_candidates <= 32 or not 1 <= len(indices) <= args.max_candidates
            or indices != [c["index"] for c in prior["candidates"] if c["score"]["accepted"]]
            or prior["source_video_sha256"] != video["source_sha256"]
            or spec["case"] != "fox-falco-battlefield-manual-v1"
            or spec["known_match"] != {"stage": 31, "characters": [2, 20]}
            or prior["window"] != [spec["checkpoint_frame"], spec["end_frame"]]):
        raise ValueError("missing complete, bounded supported coarse population")
    for sample in samples:
        image = video["frames"][sample.video_frame]
        if sha256(args.video / image["image"]) != image["image_sha256"]:
            raise ValueError("manual source image identity mismatch")
    config = RunConfig(Path("build/headless/melee_headless"), Path("build/game/melee_game.so"),
                       Path(os.environ.get("YT2SLP_ISO", "/assets/melee.iso")), Path(".local/runs"),
                       rng_seed=spec["rng_seed"], time_base=spec["time_base"], match=MatchConfig())
    boot = Path("third_party/melee-unlocked/port/scripts/native_vs.txt")
    prefix=json.loads((root/'prefix.json').read_text()) if (root/'prefix.json').exists() else None
    if spec.get('required_prefix_sha256') and (prefix is None or sha256(root/'prefix.json')!=spec['required_prefix_sha256']):
        raise ValueError('candidate population is missing its bound prefix')
    if prefix is not None:
        validate_prefix(prefix,spec,video['source_sha256'],native_identities(config,boot))
    if any(sha256(p) not in prior["identities"].values() for p in (config.host, config.game_library, config.iso, boot)):
        raise ValueError("native build/ISO/boot differs from coarse search")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "coarse-search.json").write_text(json.dumps(prior, indent=2) + "\n")
    (out / "search-spec.json").write_text(json.dumps(spec, indent=2) + "\n")
    (out / "timeline.json").write_text(json.dumps(timeline, indent=2) + "\n")
    if prefix is not None:(out/'prefix.json').write_text((root/'prefix.json').read_text())
    candidates = []
    try:
        with NativeLinuxBackend() as backend:
            backend.initialize(config)
            backend.start(boot, timeout=180)
            if prefix is None:
                advance_to(backend, spec["checkpoint_frame"])
            else:
                reproduce_prefix(backend,prefix,out/'prefix-reproduced.slp')
            checkpoint = backend.capture()
            for index in indices:
                schedule = spec["candidates"][index]
                if prior["candidates"][index]["schedule"] != schedule:
                    raise ValueError("candidate schedule differs from declared grid")
                backend.restore(checkpoint)
                trace = run_schedule(backend, schedule_from_dict(schedule), spec["end_frame"] - spec["checkpoint_frame"])
                original = json.loads((root / "trials" / f"{index:03d}.json").read_text())
                if json.loads(json.dumps([asdict(s) for s in trace])) != original["states"]:
                    raise ValueError("freshly simulated candidate differs from original trial")
                if not score_timeline(samples, trace)["accepted"] or backend.recording_status().last_frame != spec["end_frame"]:
                    raise ValueError("candidate no longer satisfies coarse cues/recording boundary")
                directory = out / f"candidate-{index:03d}"
                directory.mkdir()
                replay = directory / "candidate.slp"
                backend.record(replay)
                with (directory / "parser-result.json").open("x") as handle:
                    subprocess.run(["node", "tools/slippi-parser/validate.cjs", str(replay), "--last-frame", str(spec["end_frame"])],
                                   stdout=handle, check=True)
                if index == prior["selected_index"] and sha256(replay) != prior["selected_replay_sha256"]:
                    raise ValueError("previous selected replay bytes changed")
                candidates.append({"index": index, "schedule": schedule, "replay": str(replay.relative_to(out)),
                                   "replay_sha256": sha256(replay), "parser_validated": True,
                                   "original_trial_observations_match": True})
            native_run = str(backend.last_run_dir)
    except Exception as exc:
        (out / "export-failure.json").write_text(json.dumps({"error": str(exc), "completed": candidates}, indent=2) + "\n")
        raise
    manifest = {"schema": 1, "kind": "rendered-candidate-population", "export_passed": True,
                "source_video_sha256": video["source_sha256"], "expected_indices": indices, "candidates": candidates,
                "window": prior["window"], "capture_interval": render_interval(spec), "capture_padding": 0,
                "native_run": native_run, "iso_sha256": sha256(config.iso),
                "identities": {str(p): sha256(p) for p in (Path(__file__), root / "search-result.json", root / "search-spec.json",
                    root / "timeline.json", args.video / "video.json", config.host, config.game_library, config.iso, boot,
                    Path("src/yt2slp/search.py"), Path("tools/slippi-parser/validate.cjs"), Path("tools/slippi-parser/package-lock.json"))}}
    (out / "candidates.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"output": str(out), "exported": indices}, indent=2))


if __name__ == "__main__":
    main()
