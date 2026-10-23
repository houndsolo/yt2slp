"""Local, progressive video ingestion with explicit presentation timestamps.

This does not identify gameplay, cuts, game frames, or missing simulation ticks.
Numbered PNGs are decode indices only; time comes from the source stream PTS.
"""
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def timestamp_rows(probe: dict, max_frames: int) -> tuple[dict, list[dict]]:
    streams = probe.get("streams", [])
    frames = probe.get("frames", [])
    if len(streams) != 1 or not frames or len(frames) > max_frames:
        raise ValueError("expected one selected video stream and 1..max_frames decoded frames")
    stream = streams[0]
    base = Fraction(stream["time_base"])
    if base <= 0 or any(s.get("rotation", 0) for s in stream.get("side_data_list", [])):
        raise ValueError("invalid time base or unsupported rotated video")
    if stream.get("tags", {}).get("rotate", "0") != "0":
        raise ValueError("rotated video is not supported")
    rows = []
    for index, frame in enumerate(frames):
        # Do not synthesize missing timestamps from a nominal frame rate.
        raw = frame.get("pts")
        if type(raw) is not int or frame.get("interlaced_frame") != 0:
            raise ValueError("missing integer presentation timestamp or unsupported interlaced video")
        if frame.get("best_effort_timestamp", raw) != raw:
            raise ValueError("decoder best-effort timestamp differs from source PTS")
        if [frame.get("width"), frame.get("height")] != [stream["width"], stream["height"]]:
            raise ValueError("changing frame dimensions are not supported")
        if rows and raw <= rows[-1]["pts"]:
            raise ValueError("presentation timestamps must be strictly increasing")
        rows.append({"index": index, "pts": raw, "time_seconds": str(raw * base),
                     "relative_seconds": str((raw - frames[0]["pts"]) * base)})
    return stream, rows


def ingest_video(source: Path, output: Path, max_frames: int = 1800) -> dict:
    if type(max_frames) is not int or not 1 <= max_frames <= 18000:
        raise ValueError("max_frames must be in 1..18000; trim long videos first")
    source = source.resolve()
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-show_frames",
        "-of", "json", str(source)], timeout=120))
    stream, rows = timestamp_rows(probe, max_frames)
    output.mkdir(parents=True, exist_ok=False)
    images = output / "frames"
    images.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-noautorotate", "-i", str(source), "-map", "0:v:0",
                    "-fps_mode", "passthrough", "-threads", "1", "-start_number", "0",
                    str(images / "%06d.png")], check=True, timeout=180)
    if len(list(images.glob("*.png"))) != len(rows):
        raise ValueError("FFmpeg decode and probed frame counts disagree")
    previous = None
    for row in rows:
        path = images / f'{row["index"]:06d}.png'
        digest = sha256(path)
        row.update(image=str(path.relative_to(output)), image_sha256=digest,
                   identical_previous_decoded_png=digest == previous)
        previous = digest
    deltas = [b["pts"] - a["pts"] for a, b in zip(rows, rows[1:])]
    manifest = {"schema": 1, "kind": "local-video", "source": str(source),
                "source_sha256": sha256(source), "time_base": stream["time_base"],
                "timestamp_field": "pts", "width": stream["width"],
                "height": stream["height"], "codec": stream["codec_name"], "frames": rows,
                "reported_average_frame_rate": stream.get("avg_frame_rate"),
                "variable_timestamp_spacing": len(set(deltas)) > 1,
                "cuts_assessed": False, "dropped_game_frames_assessed": False,
                "game_frame_alignment": None, "gameplay_crop": None,
                "identities": {str(Path(__file__)): sha256(Path(__file__))},
                "tools": {name: subprocess.check_output([name, "-version"], text=True).splitlines()[0]
                          for name in ("ffmpeg", "ffprobe")}}
    (output / "video.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def window_view(source: Path, output: Path, first: int, last: int) -> dict:
    """A contiguous decode-index view; preserve original PTS and source-video identity."""
    source, output = source.resolve(), output.resolve()
    parent = json.loads((source/'video.json').read_text())
    if (parent.get('schema') != 1 or parent.get('kind') != 'local-video'
            or type(first) is not int or type(last) is not int or not 0 <= first <= last < len(parent['frames'])):
        raise ValueError('invalid contiguous video window')
    selected = parent['frames'][first:last+1]
    for row in selected:
        if sha256(source/row['image']) != row['image_sha256']:
            raise ValueError('source image identity differs before creating window view')
    output.mkdir(parents=True,exist_ok=False)
    (output/'frames').mkdir()
    rows=[]
    for index,row in enumerate(selected):
        image=output/'frames'/f'{index:06d}.png'
        image.symlink_to(os.path.relpath(source/row['image'],image.parent))
        rows.append({**row,'index':index,'source_decode_index':row.get('source_decode_index',row['index']),
            'image':str(image.relative_to(output)),
            'identical_previous_decoded_png':False if index==0 else row['identical_previous_decoded_png']})
    document={**parent,'frames':rows,'view':{'parent_video_json_sha256':sha256(source/'video.json'),
        'parent_decode_interval':[first,last],'policy':'contiguous view; original PTS, source-relative time and image hashes retained'}}
    (output/'video.json').write_text(json.dumps(document,indent=2)+'\n')
    return document
