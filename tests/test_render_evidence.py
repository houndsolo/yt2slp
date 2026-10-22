"""Synthetic image-region metrics; real candidate Playback is checked separately."""
from copy import deepcopy
import subprocess

import pytest

from yt2slp.render_evidence import (crop_rgb, decode_rgb, load_regions, rank_region_scores,
                                    squared_error, translation_diagnostic)


def video_and_regions():
    video = {"source_sha256": "video", "width": 100, "height": 80,
             "frames": [{"image_sha256": "image"}]}
    document = {"schema": 1, "kind": "manual-image-regions", "video_sha256": "video",
                "objective": "equal-region-unshifted-rgb-mse-v1", "translation_radius": 8, "regions": [
                    {"name": "fighter", "role": "fighter", "video_frame": 0, "image_sha256": "image", "box": [10, 10, 20, 20], "source": "synthetic region annotation"},
                    {"name": "stage", "role": "stage", "video_frame": 0, "image_sha256": "image", "box": [40, 10, 12, 12], "source": "synthetic region annotation"}]}
    return video, document


def test_region_annotations_bind_images_and_keep_fighter_and_stage_evidence():
    video, document = video_and_regions()
    loaded = load_regions(document, video)
    assert len(loaded) == 2
    loaded[0]["box"][0] = 80
    assert document["regions"][0]["box"][0] == 10
    document["regions"][0]["image_sha256"] = "changed"
    with pytest.raises(ValueError, match="identity"): load_regions(document, video)


@pytest.mark.parametrize("mutation", ["video", "policy", "outside", "no_margin", "float", "duplicate", "one_role", "empty_source"])
def test_unusable_or_unreviewable_regions_are_rejected(mutation):
    video, document = video_and_regions()
    r = document["regions"][0]
    if mutation == "video": document["video_sha256"] = "other"
    if mutation == "policy": document["objective"] = "shift-until-it-matches"
    if mutation == "outside": r["box"] = [90, 10, 20, 20]
    if mutation == "no_margin": r["box"][0] = 0
    if mutation == "float": r["box"][0] = 10.5
    if mutation == "duplicate": document["regions"][1]["name"] = r["name"]
    if mutation == "one_role": document["regions"][1]["role"] = "fighter"
    if mutation == "empty_source": r["source"] = " "
    with pytest.raises(ValueError): load_regions(document, video)


def test_translation_is_diagnostic_and_does_not_erase_unshifted_error():
    width = height = 40
    source = bytes(v for y in range(height) for x in range(width) for v in (x*3, y*4, (x*5+y*7) % 256))
    shifted = bytes(v for y in range(height) for x in range(width)
                    for v in ((max(0, x-3)*3, y*4, (max(0, x-3)*5+y*7) % 256)))
    box = (12, 12, 12, 12)
    patch = crop_rgb(source, width, height, box)
    diagnostic = translation_diagnostic(patch, shifted, width, height, box)
    assert diagnostic["best_offsets_xy"] == [[3, 0]] and not diagnostic["ambiguous"]
    assert not diagnostic["at_search_boundary"]
    assert squared_error(patch, crop_rgb(shifted, width, height, box)) > 0


def test_flat_patch_translation_stays_ambiguous():
    data = bytes(40*40*3)
    diagnostic = translation_diagnostic(bytes(12*12*3), data, 40, 40, (12, 12, 12, 12))
    assert diagnostic["ambiguous"] and len(diagnostic["best_offsets_xy"]) == 17*17


def candidate(index, a, b, counts=(1, 1)):
    return {"index": index, "regions": [
        {"name": "fighter", "squared_error": a, "channels": counts[0]},
        {"name": "stage", "squared_error": b, "channels": counts[1]}]}


def test_equal_region_weight_keeps_large_background_regions_from_dominating():
    report = rank_region_scores([candidate(3, 0, 100, (1000, 1)), candidate(8, 10000, 0, (1000, 1))], [3, 8], ["fighter", "stage"])
    assert report["ranked_indices"] == [8, 3]
    assert report["metrics"]["8"]["equal_region_mse"] == 5
    assert not report["visual_accuracy_accepted"] and report["absolute_acceptance_threshold"] is None


def test_exact_rational_ties_are_retained_without_float_rounding_false_ties():
    report = rank_region_scores([candidate(3, 1, 1, (3, 3)), candidate(8, 2, 2, (6, 6))], [3, 8], ["fighter", "stage"])
    assert report["equally_best_indices"] == [3, 8] and report["selected_index"] == 3
    huge = 2**60
    report = rank_region_scores([candidate(3, huge+1, huge+1, (huge, huge)), candidate(8, 1, 1)], [3, 8], ["fighter", "stage"])
    assert report["equally_best_indices"] == [8]


@pytest.mark.parametrize("mutation", ["missing_candidate", "duplicate_candidate", "missing_region", "duplicate_region", "negative", "nonfinite", "empty"])
def test_incomplete_or_invalid_populations_never_publish_a_best_candidate(mutation):
    candidates = [candidate(3, 1, 2), candidate(8, 3, 4)]
    if mutation == "missing_candidate": candidates.pop()
    if mutation == "duplicate_candidate": candidates[1]["index"] = 3
    if mutation == "missing_region": candidates[0]["regions"].pop()
    if mutation == "duplicate_region": candidates[0]["regions"][1] = deepcopy(candidates[0]["regions"][0])
    if mutation == "negative": candidates[0]["regions"][0]["squared_error"] = -1
    if mutation == "nonfinite": candidates[0]["regions"][0]["squared_error"] = float("nan")
    if mutation == "empty": candidates[0]["regions"][0]["channels"] = 0
    with pytest.raises(ValueError): rank_region_scores(candidates, [3, 8], ["fighter", "stage"])


def test_real_png_decode_excludes_alpha_and_preserves_geometry(tmp_path):
    image = tmp_path / "synthetic.png"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:size=32x32", "-vf", "format=rgba",
                    "-frames:v", "1", str(image)], check=True)
    rgb = decode_rgb(image, 32, 32)
    assert len(rgb) == 32*32*3 and rgb[0] > 200 and rgb[1] < 10
    with pytest.raises(ValueError, match="no resizing"): decode_rgb(image, 34, 32)
