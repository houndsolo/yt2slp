"""Decode a short local video; retain source PTS, images and explicit unknowns."""
import argparse
from pathlib import Path

from yt2slp.video import ingest_video


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-frames", type=int, default=1800)
    args = parser.parse_args()
    result = ingest_video(args.video, args.output, args.max_frames)
    print(f'{args.output / "video.json"}: {len(result["frames"])} frames; no game-frame alignment inferred')


if __name__ == "__main__":
    main()
