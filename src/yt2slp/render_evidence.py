"""Source-bound image regions for ranking genuine rendered input hypotheses.

Unshifted RGB error is the objective. A sparse patch translation diagnostic is
reported separately and never used to shift images, fit camera state or score.
No world-coordinate/root-position measurement or visual acceptance is implied.
"""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import math
import subprocess
import tempfile

from .timer_labels import label_images, png_size
from .timeline import apply_manual_timer_labels, check_rendered_clock_timing
from .video import sha256


def label_source(video_dir, video, calibration, timers, first, last, manual=None):
    """Keep automatic failures and individually sourced timer readings separate."""
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        for index, row in enumerate(video["frames"], 1):
            source = video_dir / row["image"]
            if sha256(source) != row["image_sha256"]:
                raise ValueError("source image identity differs from ingested video")
            (folder / f"framedump_{index}.png").symlink_to(source.resolve())
        labels = label_images(folder, calibration, timers, first, last)
    for row in labels["records"]:
        index = int(Path(row["image"]).stem.split("_")[-1]) - 1
        row.update(video_frame=index, pts=video["frames"][index]["pts"], image=video["frames"][index]["image"])
    labels["selected"] = {frame: video["frames"][int(Path(alias).stem.split("_")[-1]) - 1]["image"]
                          for frame, alias in labels["selected"].items()}
    automatic = deepcopy(labels)
    if manual is not None:
        labels = apply_manual_timer_labels(labels, manual, video, timers, first, last)
    return automatic, labels, check_rendered_clock_timing(labels, video)


def load_regions(document, video):
    if (document.get("schema") != 1 or document.get("kind") != "manual-image-regions"
            or document.get("video_sha256") != video["source_sha256"]
            or document.get("objective") != "equal-region-unshifted-rgb-mse-v1"
            or document.get("translation_radius") != 8):
        raise ValueError("unsupported source identity or fixed image-region policy")
    regions = document["regions"]
    if not isinstance(regions, list) or not 2 <= len(regions) <= 64:
        raise ValueError("expected 2..64 manual image regions")
    names = set()
    roles = set()
    for region in regions:
        name, index, box = region["name"], region["video_frame"], region["box"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("region names must be nonempty and unique")
        names.add(name)
        if type(index) is not int or not 0 <= index < len(video["frames"]):
            raise ValueError("invalid source video frame")
        if region["image_sha256"] != video["frames"][index]["image_sha256"]:
            raise ValueError("region annotation image identity mismatch")
        if region["role"] not in ("fighter", "stage") or not isinstance(region.get("source"), str) or not region["source"].strip():
            raise ValueError("region needs an explicit role and manual source")
        roles.add(region["role"])
        if not isinstance(box, list) or len(box) != 4 or any(type(v) is not int for v in box):
            raise ValueError("region box requires integer x,y,width,height")
        x, y, w, h = box
        if not (8 <= x and 8 <= y and 8 <= w <= 128 and 8 <= h <= 128
                and x+w+8 <= video["width"] and y+h+8 <= video["height"]):
            raise ValueError("region must fit geometry and the fixed translation diagnostic margin")
    if roles != {"fighter", "stage"}:
        raise ValueError("both fighter and stage regions are required")
    return deepcopy(regions)


def decode_rgb(path, width, height):
    if png_size(path) != [width, height]:
        raise ValueError("source/candidate image dimensions differ; no resizing permitted")
    data = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1",
                                    "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], timeout=30)
    if len(data) != width*height*3:
        raise ValueError("incomplete decoded RGB frame")
    return data


def crop_rgb(data, width, height, box):
    x, y, w, h = box
    if len(data) != width*height*3 or not (0 <= x and 0 <= y and w > 0 and h > 0 and x+w <= width and y+h <= height):
        raise ValueError("invalid RGB buffer/region geometry")
    return b"".join(data[((y+row)*width+x)*3:((y+row)*width+x+w)*3] for row in range(h))


def squared_error(a, b):
    if not a or len(a) != len(b):
        raise ValueError("pixel buffers must be nonempty and equally sized")
    return sum((x-y)*(x-y) for x, y in zip(a, b))


def translation_diagnostic(source_patch, candidate, width, height, box, radius=8):
    """Sparse RGB SSD; ambiguous/equal minima stay explicit. No scale/pose fit."""
    x, y, w, h = box
    if len(source_patch) != w*h*3:
        raise ValueError("invalid source template size")
    # One sample every four pixels per axis; these are not probabilities.
    offsets = [(yy*w+xx)*3+c for yy in range(0, h, 4) for xx in range(0, w, 4) for c in range(3)]
    reference = bytes(source_patch[i] for i in offsets)
    errors = []
    for dy in range(-radius, radius+1):
        for dx in range(-radius, radius+1):
            patch = crop_rgb(candidate, width, height, (x+dx, y+dy, w, h))
            errors.append((squared_error(reference, bytes(patch[i] for i in offsets)), dx, dy))
    minimum = min(e[0] for e in errors)
    best = [[dx, dy] for error, dx, dy in errors if error == minimum]
    return {"best_offsets_xy": best, "ambiguous": len(best) != 1,
            "sparse_rmse": math.sqrt(minimum/len(reference)), "radius_pixels": radius,
            "at_search_boundary": any(abs(dx) == radius or abs(dy) == radius for dx, dy in best),
            "policy": "translation-only sparse patch diagnostic; never applied to objective/images; not a fighter-root measurement"}


def rank_region_scores(candidates, expected_indices, region_names):
    """Every declared candidate/region must be present; no silent subset ranking."""
    if (not expected_indices or len(set(expected_indices)) != len(expected_indices)
            or not region_names or len(set(region_names)) != len(region_names)):
        raise ValueError("invalid candidate/region population")
    by_index = {}
    for candidate in candidates:
        index = candidate["index"]
        if index in by_index or index not in expected_indices:
            raise ValueError("unexpected/duplicate candidate")
        records = candidate["regions"]
        if (len(records) != len(region_names) or {r["name"] for r in records} != set(region_names)):
            raise ValueError("incomplete/duplicate region coverage")
        score = Fraction(0)
        for region in records:
            error, count = region["squared_error"], region["channels"]
            if type(error) is not int or error < 0 or type(count) is not int or count <= 0:
                raise ValueError("invalid pixel metric")
            score += Fraction(error, count)
        by_index[index] = score/len(records)
    if set(by_index) != set(expected_indices):
        raise ValueError("missing candidate; no best-of-incomplete-grid result")
    minimum = min(by_index.values())
    best = [i for i in expected_indices if by_index[i] == minimum]
    ranking = sorted(expected_indices, key=lambda i: (by_index[i], expected_indices.index(i)))
    return {"ranked_indices": ranking, "equally_best_indices": best, "selected_index": best[0],
            "metrics": {str(i): {"equal_region_mse": float(by_index[i]), "equal_region_rmse": math.sqrt(by_index[i]),
                                 "exact_mse": str(by_index[i])} for i in expected_indices},
            "selection_policy": "minimum mean of region RGB MSEs; exact rational ties retained; first in declared order breaks ties",
            "visual_accuracy_accepted": False, "absolute_acceptance_threshold": None,
            "original_inputs_identified": False, "world_positions_measured": False}
