"""Keep official playback, scalar agreement, timer alignment and visual error separate.

Run in Docker after host capture. This fixed HUD calibration supports only the
controlled, unpaused 642x528 case. Pixel error is diagnostic, with no pass threshold.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

from yt2slp.benchmark import compare_posts
from yt2slp.timeline import apply_manual_timer_labels, check_rendered_clock_timing, load_timeline
from yt2slp.timer_labels import label_images
from yt2slp.video import sha256


def export(replay, output):
    with output.open("x") as handle:
        subprocess.run(["node", "tools/slippi-parser/export-state.cjs", str(replay)], stdout=handle, check=True)
    return json.loads(output.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manual-timers", type=Path, help="optional individually verified readings for unread source timers")
    args = parser.parse_args()
    root, video_dir = args.run.resolve(), args.video.resolve()
    search = json.loads((root / "search-result.json").read_text())
    capture = json.loads((root / "official/capture.json").read_text())
    video = json.loads((video_dir / "video.json").read_text())
    load_timeline(json.loads((root / "timeline.json").read_text()), video)
    if (not search["passed"] or not search["parser_validated"] or not search["fresh_recording_bytes_match"]
            or not capture["capture_passed"] or capture["should_resync"] is not False
            or search["source_video_sha256"] != video["source_sha256"]
            or search["selected_replay_sha256"] != sha256(root / "selected.slp")
            or capture["source_replay_sha256"] != search["selected_replay_sha256"]
            or len(capture["regenerated_replays"]) != 1):
        raise ValueError("missing successful, identity-bound search and official capture")
    # Docker and host ISO paths differ; their content identity must agree.
    if search["identities"]["/assets/melee.iso"] not in capture["identities"].values():
        raise ValueError("native/official ISO identity mismatch")
    first, last = capture["wanted_interval"]
    out = args.output.resolve() if args.output else root / "review"
    out.mkdir(exist_ok=False)
    native = export(root / "selected.slp", out / "selected-state.json")
    official = export(root / "official" / capture["regenerated_replays"][0], out / "official-state.json")
    settings = native["settings"]
    if (settings["stage"] != 31 or [p["character"] for p in settings["players"]] != [2, 20]
            or settings["timer_type"] != 2 or settings["timer_seconds"] != 120):
        raise ValueError("unsupported controlled timer case")
    state = compare_posts(native, official, first, last)
    calibration = json.loads(args.calibration.read_text())
    generated = label_images(root / "official/user/Dump/Frames", calibration, native["timers"], first, last)
    (out / "reconstruction-labels.json").write_text(json.dumps(generated, indent=2) + "\n")
    with tempfile.TemporaryDirectory(dir=out) as temporary:
        temp = Path(temporary)
        source_frames = temp / "source"
        source_frames.mkdir()
        for i, row in enumerate(video["frames"], 1):
            image = video_dir / row["image"]
            if sha256(image) != row["image_sha256"]:
                raise ValueError("source image differs from ingested identity")
            (source_frames / f"framedump_{i}.png").symlink_to(image)
        source = label_images(source_frames, calibration, native["timers"], first, last)
        # Replace temporary aliases with persistent decode indices/PTS references.
        for record in source["records"]:
            index = int(Path(record["image"]).stem.split("_")[-1]) - 1
            record.update(video_frame=index, pts=video["frames"][index]["pts"], image=video["frames"][index]["image"])
        source["selected"] = {frame: video["frames"][int(Path(alias).stem.split("_")[-1]) - 1]["image"]
                              for frame, alias in source["selected"].items()}
        (out / "source-automatic-labels.json").write_text(json.dumps(source, indent=2) + "\n")
        if args.manual_timers:
            source = apply_manual_timer_labels(source, json.loads(args.manual_timers.read_text()), video,
                                               native["timers"], first, last)
        clock = check_rendered_clock_timing(source, video)
        (out / "source-labels.json").write_text(json.dumps(source, indent=2) + "\n")
        pixel_metric = None
        clip = None
        if source["passed"] and generated["passed"] and clock["passed"]:
            a, b = temp / "a", temp / "b"
            a.mkdir(); b.mkdir()
            with (out / "comparison-index.csv").open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["comparison_frame", "rendered_game_frame", "source_image", "reconstruction_image"])
                for i, frame in enumerate(range(first, last + 1)):
                    left = video_dir / source["selected"][frame]
                    right = root / "official/user/Dump/Frames" / generated["selected"][frame]
                    (a / f"{i:06d}.png").symlink_to(left)
                    (b / f"{i:06d}.png").symlink_to(right)
                    writer.writerow([i, frame, str(left), str(right)])
            inputs = ["ffmpeg", "-v", "error", "-framerate", "60", "-i", str(a / "%06d.png"),
                      "-framerate", "60", "-i", str(b / "%06d.png")]
            subprocess.run(inputs + ["-filter_complex", "[0:v][1:v]hstack=inputs=2", "-c:v", "ffv1", "-pix_fmt", "bgra",
                                     str(out / "comparison.mkv")], check=True)
            subprocess.run(inputs + ["-filter_complex", "[0:v]format=gbrp[a];[1:v]format=gbrp[b];[a][b]psnr=stats_file=pixel-errors.log",
                                     "-f", "null", "-"], cwd=out, check=True)
            errors = [float(v) for v in re.findall(r"mse_avg:([0-9.]+)", (out / "pixel-errors.log").read_text())]
            if len(errors) != last - first + 1:
                raise ValueError("pixel diagnostic has missing frame coverage")
            pixel_metric = {"rgb_rmse_0_to_255": math.sqrt(sum(errors) / len(errors)), "frames": len(errors),
                            "definition": "whole-frame 8-bit RGB; FFmpeg per-frame MSE rounded to 2 decimals",
                            "acceptance_threshold": None, "camera_hud_background_and_compression_included": True}
            clip = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height,nb_read_frames,r_frame_rate", "-of", "json",
                str(out / "comparison.mkv")]))["streams"][0]
            if int(clip["nb_read_frames"]) != last - first + 1 or clip["r_frame_rate"] != "60/1":
                raise ValueError("comparison clip count/rate mismatch")
    report = {"schema": 1, "pipeline_checks_passed": search["passed"] and state["passed"] and source["passed"] and generated["passed"] and clock["passed"],
              "manual_cue_search_passed": search["passed"], "parser_validated": search["parser_validated"],
              "official_playback_progression_passed": capture["capture_passed"], "native_vs_official_selected_fields": state,
              "source_timer_coverage_passed": source["passed"], "reconstruction_timer_coverage_passed": generated["passed"],
              "source_automatic_timer_coverage_passed": source.get("automatic_coverage_passed", source["passed"]),
              "source_manual_timer_labels": source.get("manual_label_count", 0), "source_pts_vs_game_clock": clock,
              "source_vs_reconstruction_pixel_diagnostic": pixel_metric, "comparison_clip": clip,
              "visual_reconstruction_accepted": False, "visual_accuracy_thresholds_established": False,
              "original_inputs_identified": False, "full_state_equality_measured": False,
              "render_vs_post_update_phase_equality_established": False,
              "identities": {str(p): sha256(p) for p in (Path(__file__), args.calibration, root / "search-result.json",
                   root / "timeline.json", root / "official/capture.json", root / "selected.slp", video_dir / "video.json",
                   out / "selected-state.json", out / "official-state.json", out / "source-labels.json", out / "reconstruction-labels.json",
                   Path("src/yt2slp/timer_labels.py"), Path("src/yt2slp/timeline.py"), Path("tools/slippi-parser/export-state.cjs"),
                   Path("tools/slippi-parser/package-lock.json"), out / "source-automatic-labels.json")}}
    if args.manual_timers: report["identities"][str(args.manual_timers)] = sha256(args.manual_timers)
    if clip: report["comparison_clip_sha256"] = sha256(out / "comparison.mkv")
    (out / "review-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("pipeline_checks_passed", "source_vs_reconstruction_pixel_diagnostic", "visual_reconstruction_accepted")}, indent=2))
    return 0 if report["pipeline_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
