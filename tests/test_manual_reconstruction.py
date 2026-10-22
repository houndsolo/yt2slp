"""Synthetic cue/search tests; FFmpeg fixtures contain no Melee/game material."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import struct
import subprocess

import pytest

from yt2slp.backend import Observation
from yt2slp.evidence import Evidence, Provenance
from yt2slp.search import HorizontalSchedule, bounded_search, run_schedule
from yt2slp.timeline import (Cue, Sample, apply_manual_timer_labels, check_rendered_clock_timing,
                             load_timeline, score_timeline)
from yt2slp.video import ingest_video, timestamp_rows


def bits(value):
    return struct.unpack("!I", struct.pack("!f", value))[0]


def state(frame, x=1.0, facing=1.0, action=20):
    fighter = (1, 4, action, bits(1.0), bits(x), bits(0.0), 0, 0, 0, 0, bits(0.0), bits(facing))
    other = (1, 4, 14, bits(1.0), bits(0.0), bits(20.0), 0, 0, 0, 0, bits(0.0), bits(-1.0))
    return Observation(frame + 100, 2, 2, frame, 1, (fighter, other))


def known(value):
    return Evidence(value, Provenance.INFERRED, "synthetic annotation for unit test")


def sample(field="horizontal_order", values=None, frames=(240,)):
    return Sample(0, frames, known(list(frames)), (Cue(0, field, known(values or ["right"])),))


def probe():
    return {"streams": [{"time_base": "1/1000", "width": 16, "height": 16}],
            "frames": [{"pts": pts, "best_effort_timestamp": pts, "width": 16, "height": 16, "interlaced_frame": 0}
                       for pts in (500, 533, 600)]}


def test_preserves_variable_pts_and_original_nonzero_origin():
    _, rows = timestamp_rows(probe(), 3)
    assert [r["time_seconds"] for r in rows] == ["1/2", "533/1000", "3/5"]
    assert [r["relative_seconds"] for r in rows] == ["0", "33/1000", "1/10"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reversed", "best_effort", "interlaced", "dimensions", "rotation", "limit"])
def test_rejects_unsupported_or_ambiguous_source_timing(mutation):
    data = probe()
    if mutation == "missing": del data["frames"][1]["pts"]
    if mutation == "duplicate": data["frames"][1].update(pts=500, best_effort_timestamp=500)
    if mutation == "reversed": data["frames"][1].update(pts=499, best_effort_timestamp=499)
    if mutation == "best_effort": data["frames"][1]["best_effort_timestamp"] = 534
    if mutation == "interlaced": data["frames"][1]["interlaced_frame"] = 1
    if mutation == "dimensions": data["frames"][1]["width"] = 18
    if mutation == "rotation": data["streams"][0]["side_data_list"] = [{"rotation": 90}]
    with pytest.raises(ValueError): timestamp_rows(data, 2 if mutation == "limit" else 3)


def test_real_ffmpeg_ingestion_keeps_duplicate_images_and_rejects_overwrite(tmp_path):
    source, output = tmp_path / "synthetic.mp4", tmp_path / "decoded"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:size=16x16:rate=30",
                    "-frames:v", "3", "-c:v", "libx264", str(source)], check=True)
    result = ingest_video(source, output)
    assert len(result["frames"]) == 3
    assert [f["relative_seconds"] for f in result["frames"]] == ["0", "1/30", "1/15"]
    assert [f["identical_previous_decoded_png"] for f in result["frames"]] == [False, True, True]
    assert result["game_frame_alignment"] is None and not result["dropped_game_frames_assessed"]
    assert json.loads((output / "video.json").read_text()) == result
    with pytest.raises(FileExistsError): ingest_video(source, output)


def test_real_variable_rate_decode_does_not_insert_a_missing_frame(tmp_path):
    source = tmp_path / "variable.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=16x16:rate=30",
                    "-vf", "select='not(eq(n,2))'", "-fps_mode", "vfr", "-frames:v", "4", "-c:v", "libx264", str(source)], check=True)
    result = ingest_video(source, tmp_path / "decoded")
    assert [f["relative_seconds"] for f in result["frames"]] == ["0", "1/30", "1/10", "2/15"]
    assert result["variable_timestamp_spacing"]


def annotation():
    video = {"schema": 1, "kind": "local-video", "source_sha256": "video-hash",
             "frames": [{"image_sha256": "image-hash"}]}
    doc = {"schema": 1, "kind": "manual-visual-cues", "video_sha256": "video-hash", "samples": [
        {"video_frame": 0, "image_sha256": "image-hash", "alignment": {
            "value": [240, 241], "provenance": "inferred", "source": "timer annotation"}, "cues": [
            {"player": 0, "field": "horizontal_order", "evidence": {
                "value": ["right"], "provenance": "observed", "source": "manual player ordering"}}]}]}
    return doc, video


def test_manual_annotations_bind_video_image_identity_and_explicit_uncertainty():
    doc, video = annotation()
    loaded = load_timeline(doc, video)
    assert loaded[0].game_frames == (240, 241)
    for target, field in ((doc, "video_sha256"), (doc["samples"][0], "image_sha256")):
        old = target[field]
        target[field] = "changed"
        with pytest.raises(ValueError): load_timeline(doc, video)
        target[field] = old


@pytest.mark.parametrize("mutation", ["unknown_only", "hidden_field", "empty_source", "duplicate_cue", "overlap", "bad_value"])
def test_manual_timeline_rejects_unusable_or_conflicting_schema(mutation):
    doc, video = annotation()
    raw = doc["samples"][0]
    cue = raw["cues"][0]
    if mutation == "unknown_only": cue["evidence"].update(value=None, provenance="unknown")
    if mutation == "hidden_field": cue["field"] = "rng"
    if mutation == "empty_source": cue["evidence"]["source"] = " "
    if mutation == "duplicate_cue": raw["cues"].append(deepcopy(cue))
    if mutation == "bad_value": cue["evidence"]["value"] = ["approximately right"]
    if mutation == "overlap":
        video["frames"].append(deepcopy(video["frames"][0]))
        doc["samples"].append({**deepcopy(raw), "video_frame": 1})
    with pytest.raises(ValueError): load_timeline(doc, video)


def test_one_sample_cannot_mix_cues_from_different_uncertain_frames():
    s = sample(frames=(240, 241))
    s = replace(s, cues=s.cues + (Cue(0, "facing", known(["right"])),))
    result = score_timeline((s,), (state(240, x=1, facing=-1), state(241, x=-1, facing=1)))
    assert result["violations"] == 1 and not result["accepted"]
    assert result["samples"][0]["equally_best_frames"] == [240, 241]


def test_unknown_values_are_unscored_and_missing_coverage_does_not_help():
    s = sample(frames=(240, 241))
    s = replace(s, cues=s.cues + (Cue(0, "damage", Evidence(None, Provenance.UNKNOWN, "HUD obscured")),))
    result = score_timeline((s,), (state(240), state(241)))
    assert result["accepted"] and result["unknown_cues"] == 1 and result["known_cues"] == 1
    with pytest.raises(ValueError, match="missing"): score_timeline((s,), (state(240),))
    with pytest.raises(ValueError, match="duplicate"): score_timeline((s,), (state(240), state(240)))


def test_ambiguous_action_alternatives_are_not_forced_to_single_state():
    s = sample("action_group", ["ground_locomotion", "airborne"])
    assert score_timeline((s,), (state(240, action=29),))["accepted"]
    assert not score_timeline((s,), (state(240, action=14),))["accepted"]


class SyntheticBranchBackend:
    """Control-only test double; deliberately cannot write a replay file."""
    def __init__(self):
        self.current = state(239, x=0, action=14)
        self.restores = 0
        self.captures = 0

    def observe(self): return self.current

    def capture(self):
        self.captures += 1
        self.saved = self.current
        return b"unit-test-handle"

    def restore(self, handle):
        assert handle == b"unit-test-handle"
        self.restores += 1
        self.current = self.saved

    def step(self, pads):
        self.current = state(self.current.match_frame + 1, x=float(pads[0].stick_x),
                             facing=1 if pads[0].stick_x >= 0 else -1,
                             action=20 if pads[0].stick_x else 14)
        return self.current

    def record(self, path): raise AssertionError("search must not export trial recordings")


def test_search_restores_selected_branch_after_last_rejected_trial_and_retains_ties(tmp_path):
    backend = SyntheticBranchBackend()
    candidates = tuple(HorizontalSchedule(0, x) for x in (64, 80, 0, -80))
    result = bounded_search(backend, (sample(),), candidates, 2, tmp_path / "trials")
    assert result["passed"] and result["accepted_indices"] == [0, 1] and result["selected_index"] == 0
    assert result["selected_schedule"]["stick_x"] == 64 and backend.current == state(241, x=64)
    assert backend.restores == 5 and backend.captures == 1
    assert len(list((tmp_path / "trials").glob("*.json"))) == 4
    assert not result["original_inputs_identified"]


def test_failed_search_preserves_trials_and_restores_checkpoint_without_export(tmp_path):
    backend = SyntheticBranchBackend()
    result = bounded_search(backend, (sample("action_group", ["airborne"]),),
                            (HorizontalSchedule(0, 80), HorizontalSchedule(0, -80)), 2, tmp_path / "trials")
    assert not result["passed"] and result["selected_index"] is None
    assert backend.current.match_frame == 239


def test_search_validates_budget_and_window_before_capturing(tmp_path):
    backend = SyntheticBranchBackend()
    for candidates, steps in (((), 2), ((HorizontalSchedule(0, 80),), 601),
                              ((HorizontalSchedule(0, 80),) * 2, 2)):
        with pytest.raises(ValueError): bounded_search(backend, (sample(),), candidates, steps, tmp_path / "trials")
    with pytest.raises(ValueError):
        bounded_search(backend, (sample(frames=(300,)),), (HorizontalSchedule(0, 80),), 2, tmp_path / "trials")
    assert backend.captures == 0


def test_search_rejects_stalled_match_time_instead_of_assuming_vi_alignment():
    backend = SyntheticBranchBackend()
    backend.step = lambda pads: backend.current
    with pytest.raises(ValueError, match="no offset guessed"):
        run_schedule(backend, HorizontalSchedule(0, 80), 1)


def test_manual_timer_fill_retains_unknown_automatic_result_and_binds_source():
    automatic = {"records": [{"video_frame": 0, "image": "frame.png", "frame": None}],
                 "selected": {}, "passed": False, "method": "calibrated timer"}
    video = {"source_sha256": "video", "frames": [{"image_sha256": "image"}]}
    manual = {"schema": 1, "kind": "manual-timer-labels", "video_sha256": "video", "labels": [
        {"video_frame": 0, "image_sha256": "image", "evidence": {
            "value": "01:56.00", "provenance": "observed", "source": "manual image reading"}}]}
    result = apply_manual_timer_labels(automatic, manual, video, {"240": "01:56.00"}, 240, 240)
    assert result["passed"] and not result["automatic_coverage_passed"] and result["manual_label_count"] == 1
    assert result["records"][0]["automatic_frame"] is None and automatic["records"][0]["frame"] is None
    manual["labels"][0]["image_sha256"] = "changed"
    with pytest.raises(ValueError, match="identity"):
        apply_manual_timer_labels(automatic, manual, video, {"240": "01:56.00"}, 240, 240)


def test_manual_timer_cannot_silently_replace_a_conflicting_automatic_label():
    automatic = {"records": [{"video_frame": 0, "frame": 241}], "passed": False}
    video = {"source_sha256": "video", "frames": [{"image_sha256": "image"}]}
    manual = {"schema": 1, "kind": "manual-timer-labels", "video_sha256": "video", "labels": [
        {"video_frame": 0, "image_sha256": "image", "evidence": {
            "value": "01:56.00", "provenance": "observed", "source": "manual image reading"}}]}
    with pytest.raises(ValueError, match="contradicts"):
        apply_manual_timer_labels(automatic, manual, video, {"240": "01:56.00"}, 240, 240)


def test_clock_alignment_rejects_speed_changes_without_fitting_them_away():
    labels = {"records": [{"video_frame": i, "frame": 240 + i} for i in range(3)],
              "selected": {240: "0.png", 241: "1.png", 242: "2.png"}}
    video = {"time_base": "1/600", "frames": [{"pts": i * 10} for i in range(3)]}
    assert check_rendered_clock_timing(labels, video)["passed"]
    video["frames"][-1]["pts"] = 40
    assert not check_rendered_clock_timing(labels, video)["passed"]
