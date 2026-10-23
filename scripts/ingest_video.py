"""Decode a short local video; retain source PTS, images and explicit unknowns."""
import argparse
from pathlib import Path

from yt2slp.video import ingest_video


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-frames", type=int, default=1800)
    parser.add_argument("--first", type=int, help="inclusive original decode index; requires --last")
    parser.add_argument("--last", type=int, help="inclusive original decode index; requires --first")
    parser.add_argument("--crop", type=int, nargs=4, metavar=('X', 'Y', 'WIDTH', 'HEIGHT'),
                        help="explicit pixel crop, without resizing or automatic gameplay detection")
    args = parser.parse_args()
    if (args.first is None) != (args.last is None):parser.error('--first and --last must be supplied together')
    interval = None if args.first is None else (args.first, args.last)
    result = ingest_video(args.video, args.output, args.max_frames, decode_interval=interval,
                          crop=None if args.crop is None else tuple(args.crop))
    print(f'{args.output / "video.json"}: {len(result["frames"])} frames; no game-frame alignment inferred')


if __name__ == "__main__":
    main()
