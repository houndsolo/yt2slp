"""Join official prepared images and supervised labels without guessing phase."""
import argparse
from pathlib import Path

from yt2slp.learning_data import build_pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'labels', 'split-plan', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--context', type=int, default=31)
    args = parser.parse_args()
    result = build_pairs(args.video, args.labels, args.split_plan, args.output, args.context)
    print(f"{args.output}/pairs.json: {len(result['frames'])} frames, "
          f"{len(result['window_centers'])} {result['split']} windows; "
          "image/post phase remains unverified, smoke tests only")


if __name__ == '__main__':
    main()
