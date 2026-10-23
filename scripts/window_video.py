"""Create a timestamp-preserving window of an ingested video; no re-encoding."""
import argparse
from pathlib import Path
from yt2slp.video import window_view

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--first',type=int,required=True,help='inclusive parent decode index')
    p.add_argument('--last',type=int,required=True,help='inclusive parent decode index')
    a=p.parse_args();window_view(a.video,a.output,a.first,a.last)
    print(a.output/'video.json')

if __name__=='__main__':main()
