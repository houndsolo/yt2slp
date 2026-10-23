"""Create an explicit fixed-size image view, retaining source timestamps."""
import argparse
from pathlib import Path
from yt2slp.video import resize_view


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('width', 'height'):
        parser.add_argument('--'+name, type=int, required=True)
    args = parser.parse_args()
    resize_view(args.video, args.output, args.width, args.height)
    print(args.output/'video.json')


if __name__ == '__main__':
    main()
