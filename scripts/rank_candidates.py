"""Rank all coarse-accepted replays using source-only image regions, in Docker."""
import argparse
import csv
import json
from pathlib import Path
import re
import subprocess

from yt2slp.benchmark import compare_posts, validate_match_settings
from yt2slp.render_evidence import (crop_rgb, decode_rgb, label_source, load_regions,
                                    rank_region_scores, squared_error, translation_diagnostic)
from yt2slp.timer_labels import label_images
from yt2slp.video import sha256


def export_state(replay, output):
    with output.open("x") as handle:
        subprocess.run(["node", "tools/slippi-parser/export-state.cjs", str(replay)], stdout=handle, check=True)
    return json.loads(output.read_text())


def rank(args):
    root, video_dir = args.candidates.resolve(), args.video.resolve()
    population = json.loads((root / "candidates.json").read_text())
    video = json.loads((video_dir / "video.json").read_text())
    regions_document = json.loads(args.regions.read_text())
    regions = load_regions(regions_document, video)
    if (population.get("kind") != "rendered-candidate-population" or not population["export_passed"]
            or population["source_video_sha256"] != video["source_sha256"]
            or population["expected_indices"] != [c["index"] for c in population["candidates"]]):
        raise ValueError("unsupported or incomplete candidate population")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "regions.json").write_text(args.regions.read_text())
    results = []
    identities = {str(p): sha256(p) for p in (Path(__file__), args.regions, args.calibration, video_dir / "video.json",
                  root / "candidates.json", root / "coarse-search.json", Path("src/yt2slp/render_evidence.py"),
                  Path("src/yt2slp/benchmark.py"), Path("src/yt2slp/timer_labels.py"), Path("src/yt2slp/timeline.py"),
                  Path("tools/slippi-parser/export-state.cjs"), Path("tools/slippi-parser/package-lock.json"))}
    if args.manual_timers: identities[str(args.manual_timers)] = sha256(args.manual_timers)
    if args.source_calibration: identities[str(args.source_calibration)] = sha256(args.source_calibration)
    try:
        calibration = json.loads(args.calibration.read_text())
        source_calibration = json.loads(args.source_calibration.read_text()) if args.source_calibration else calibration
        first, last = population["capture_interval"]
        settings = None
        source_rgb = {}
        source_frame_ids = None
        playback_sys = None
        for candidate in population["candidates"]:
            index = candidate["index"]
            replay = root / candidate["replay"]
            official_dir = replay.parent / "official"
            capture_file = official_dir / "capture.json"
            capture = json.loads(capture_file.read_text())
            if (not candidate["parser_validated"] or sha256(replay) != candidate["replay_sha256"]
                    or not capture["capture_passed"] or capture["should_resync"] is not False
                    or capture["playback_version"] != "3.5.2" or capture["wanted_interval"] != [first, last]
                    or capture["source_replay_sha256"] != candidate["replay_sha256"]
                    or population["iso_sha256"] not in capture["identities"].values()
                    or len(capture["regenerated_replays"]) != 1):
                raise ValueError("missing identity-bound parser/official capture for candidate")
            this_sys = capture["identities"]["packaged_sys_tree"]
            if playback_sys is not None and this_sys != playback_sys:
                raise ValueError("candidate official system files differ")
            playback_sys = this_sys
            native_file, official_file = out / f"native-{index:03d}.json", out / f"official-{index:03d}.json"
            native = export_state(replay, native_file)
            official = export_state(official_dir / capture["regenerated_replays"][0], official_file)
            state_check = compare_posts(native, official, first, last, player_indices=tuple(population.get('player_ports', (0, 1))))
            if not state_check["passed"]:
                raise ValueError("native/official selected-state disagreement; no visual winner selected")
            if settings is None:
                settings = native["settings"]
                if 'requested_match' in population:
                    validate_match_settings(settings, population['requested_match'])
                elif (settings["stage"] != 31 or [p["character"] for p in settings["players"]] != [2, 20]
                      or settings["timer_type"] != 2 or settings["timer_seconds"] != 120):
                    raise ValueError("unsupported unpaused timer case")
                manual = json.loads(args.manual_timers.read_text()) if args.manual_timers else None
                automatic, source, clock = label_source(video_dir, video, source_calibration, native["timers"], first, last, manual)
                (out / "source-automatic-labels.json").write_text(json.dumps(automatic, indent=2) + "\n")
                (out / "source-labels.json").write_text(json.dumps(source, indent=2) + "\n")
                if not source["passed"] or not clock["passed"]:
                    raise ValueError("source timer coverage/clock check failed; manual readings may be required")
                source_frame_ids = {r["video_frame"]: r["frame"] for r in source["records"]}
                for region in regions:
                    i = region["video_frame"]
                    if source_frame_ids[i] is None or not first <= source_frame_ids[i] <= last:
                        raise ValueError("source region has no verified rendered game-frame label")
                    if i not in source_rgb:
                        source_rgb[i] = decode_rgb(video_dir / video["frames"][i]["image"], video["width"], video["height"])
            elif native["settings"] != settings:
                raise ValueError("candidate match settings differ")
            labels = label_images(official_dir / "user/Dump/Frames", calibration, native["timers"], first, last)
            labels_file = out / f"labels-{index:03d}.json"
            labels_file.write_text(json.dumps(labels, indent=2) + "\n")
            if not labels["passed"]:
                raise ValueError("candidate rendered frame coverage is incomplete")
            candidate_rgb = {}
            scored = []
            for region in regions:
                i, box = region["video_frame"], region["box"]
                frame = source_frame_ids[i]
                image = official_dir / "user/Dump/Frames" / labels["selected"][frame]
                if frame not in candidate_rgb:
                    candidate_rgb[frame] = decode_rgb(image, video["width"], video["height"])
                left = crop_rgb(source_rgb[i], video["width"], video["height"], box)
                right = crop_rgb(candidate_rgb[frame], video["width"], video["height"], box)
                error = squared_error(left, right)
                scored.append({"name": region["name"], "role": region["role"], "video_frame": i, "rendered_game_frame": frame,
                               "box": box, "squared_error": error, "channels": len(left), "mse": error/len(left),
                               "candidate_image": str(image.relative_to(root)), "candidate_image_sha256": sha256(image),
                               "translation_diagnostic": translation_diagnostic(left, candidate_rgb[frame], video["width"], video["height"], box)})
            results.append({"index": index, "schedule": candidate["schedule"], "replay_sha256": candidate["replay_sha256"],
                            "regions": scored, "native_vs_official_selected_fields": state_check})
            identities.update({str(p): sha256(p) for p in (capture_file, native_file, official_file, labels_file, replay)})
        ranking = rank_region_scores(results, population["expected_indices"], [r["name"] for r in regions])
        selected = next(c for c in population["candidates"] if c["index"] == ranking["selected_index"])
        spec = json.loads((root / "search-spec.json").read_text())
        spec["candidates"] = [selected["schedule"]]
        (out / "selected-spec.json").write_text(json.dumps(spec, indent=2) + "\n")
        if (root/'prefix.json').exists():
            (out/'prefix.json').write_text((root/'prefix.json').read_text())
            identities[str(root/'prefix.json')]=sha256(root/'prefix.json')
        # Copy complete genuine bytes only after the whole declared population passes.
        source = root / selected["replay"]
        with (out / "selected.slp").open("xb") as handle:
            handle.write(source.read_bytes())
        report = {"schema": 1, "kind": "rendered-region-refinement", "refinement_checks_passed": True,
                  **ranking, "candidates": results, "expected_indices": population["expected_indices"],
                  "source_video_sha256": video["source_sha256"], "fit_video_frames": sorted(source_rgb),
                  "selected_schedule": selected["schedule"], "selected_replay_sha256": sha256(out / "selected.slp"),
                  "source_automatic_timer_coverage_passed": automatic["passed"], "source_pts_vs_game_clock": clock,
                  "identities": identities, "objective": regions_document["objective"],
                  "fit_scope": f"{len(regions)} explicit source-only regions; no fitted image translation, scaling or time offset",
                  "tool_versions": {tool: subprocess.check_output([tool, "-version"], text=True).splitlines()[0] for tool in ("ffmpeg", "ffprobe")}}
        (out / "ranking.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: report[k] for k in ("ranked_indices", "equally_best_indices", "selected_schedule", "metrics")}, indent=2))
    except Exception as exc:
        (out / "selected.slp").unlink(missing_ok=True)
        (out / "ranking-failure.json").write_text(json.dumps({"error": str(exc), "completed_candidate_indices": [c["index"] for c in results],
                                                             "visual_winner_published": False}, indent=2) + "\n")
        raise


def verify(args):
    import math
    root = args.ranking.resolve()
    run = args.run.resolve()
    ranking = json.loads((root / "ranking.json").read_text())
    search = json.loads((run / "search-result.json").read_text())
    review_dir = run / "review"
    review = json.loads((review_dir / "review-result.json").read_text())
    if (not ranking["refinement_checks_passed"] or not search["passed"] or not search["parser_validated"]
            or not search["fresh_selected_observations_match"] or not search["fresh_recording_bytes_match"]
            or not review["pipeline_checks_passed"] or not review["native_vs_official_selected_fields"]["passed"]
            or search["selected_replay_sha256"] != ranking["selected_replay_sha256"]
            or sha256(root / "selected.slp") != ranking["selected_replay_sha256"]
            or sha256(run / "selected.slp") != ranking["selected_replay_sha256"]
            or search["selected_schedule"] != ranking["selected_schedule"]
            or search["source_video_sha256"] != ranking["source_video_sha256"]):
        raise ValueError("fresh selected run and independent official review do not verify this ranking")
    labels = json.loads((review_dir / "source-labels.json").read_text())
    frame_to_index = {r["frame"]: r["video_frame"] for r in labels["records"] if r["frame"] is not None}
    with (review_dir / "comparison-index.csv").open() as handle:
        mapping = list(csv.DictReader(handle))
    values = [(int(n)-1, float(mse)) for n, mse in re.findall(r"n:(\d+)\s+mse_avg:([0-9.]+)", (review_dir / "pixel-errors.log").read_text())]
    if len(values) != len(mapping) or [n for n, _ in values] != list(range(len(mapping))):
        raise ValueError("pixel diagnostics and rendered image mapping differ")
    fit = set(ranking["fit_video_frames"])
    held_out = [mse for n, mse in values if frame_to_index[int(mapping[n]["rendered_game_frame"])] not in fit]
    if not held_out:
        raise ValueError("no held-out frames")
    oracle = None
    if args.reference_state is not None:
        reference = json.loads(args.reference_state.read_text())
        selected = json.loads((review_dir / "selected-state.json").read_text())
        interval = review["native_vs_official_selected_fields"]["interval"]
        oracle = compare_posts(reference, selected, *interval)
    report = {"schema": 1, "verification_checks_passed": oracle is None or oracle["passed"], "selected_replay_sha256": ranking["selected_replay_sha256"],
              "selected_schedule": ranking["selected_schedule"], "fit_video_frames": sorted(fit),
              "held_out_rgb_rmse": math.sqrt(sum(held_out)/len(held_out)), "held_out_frame_count": len(held_out),
              "holdout_scope": "other frames of the same source clip; not independent-match generalization",
              "whole_clip_rgb_rmse": review["source_vs_reconstruction_pixel_diagnostic"]["rgb_rmse_0_to_255"],
              "visual_accuracy_accepted": False, "absolute_acceptance_threshold": None,
              "original_inputs_identified": False, "world_positions_measured": False,
              "post_selection_reference_fields": oracle,
              "reference_policy": "optional supplied controlled-case ground truth, evaluated after selection; never used to rank candidates",
              "identities": {str(p): sha256(p) for p in (Path(__file__), root / "ranking.json", run / "search-result.json",
                  run / "selected.slp", review_dir / "review-result.json", review_dir / "source-labels.json",
                  review_dir / "comparison-index.csv", review_dir / "pixel-errors.log")}}
    if args.reference_state is not None:
        report["identities"][str(args.reference_state)] = sha256(args.reference_state)
    destination = args.output if args.output is not None else root / "verification.json"
    with destination.open("x") as handle:
        handle.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["verification_checks_passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    score = sub.add_parser("rank")
    for name in ("candidates", "video", "regions", "calibration", "output"):
        score.add_argument("--"+name, type=Path, required=True)
    score.add_argument("--manual-timers", type=Path)
    score.add_argument('--source-calibration', type=Path, help='separate explicit source HUD glyph templates; same recognition thresholds')
    check = sub.add_parser("verify")
    check.add_argument("--ranking", type=Path, required=True)
    check.add_argument("--run", type=Path, required=True)
    check.add_argument("--reference-state", type=Path, help="optional post-selection controlled-case ground truth; never an input to rank")
    check.add_argument("--output", type=Path, help="new verification JSON destination; defaults to ranking/verification.json")
    args = parser.parse_args()
    return rank(args) if args.command == "rank" else verify(args)


if __name__ == "__main__":
    raise SystemExit(main())
