#!/usr/bin/env python3
"""Exercise official Slippi Playback with a private profile; retain stdout evidence.

Run on the host (optionally under xvfb-run). Frame reports establish playback
progression, not equality of rendered or simulated state with the native engine.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dolphin', type=Path, default=os.environ.get('YT2SLP_DOLPHIN'))
    p.add_argument('--iso', type=Path, default=os.environ.get('YT2SLP_ISO'))
    p.add_argument('--replay', type=Path, required=True)
    p.add_argument('--last-frame', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout', type=float, default=180)
    args = p.parse_args()
    if args.last_frame < 0 or not math.isfinite(args.timeout) or args.timeout <= 0:
        p.error("last frame must be nonnegative and timeout finite and positive")
    for value in (args.dolphin, args.iso, args.replay):
        if value is None or not value.is_file():
            p.error(f'missing input: {value}')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    user = out / 'user'
    (user / 'Config').mkdir(parents=True)
    (user / 'Config/Dolphin.ini').write_text(
        '[Core]\nCPUThread = False\nDSPHLE = True\nGFXBackend = OGL\n'
        '[Interface]\nConfirmStop = False\n[DSP]\nBackend = No audio output\n')
    request = out / 'request.json'
    request.write_text(json.dumps({'mode': 'normal', 'replay': str(args.replay.resolve()),
        'commandId': 'yt2slp-validation', 'startFrame': -123,
        'endFrame': args.last_frame, 'shouldResync': False}, indent=2)+'\n')
    command = [str(args.dolphin.resolve()), '--exec='+str(args.iso.resolve()),
        '--slippi-input='+str(request), '--user='+str(user), '--batch', '--cout']
    frames = []
    try:
        with (out / 'stdout.log').open('wb') as log:
            proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            try:
                deadline = time.monotonic() + args.timeout
                while time.monotonic() < deadline:
                    text = (out / 'stdout.log').read_text(errors='replace')
                    frames = [int(n) for n in re.findall(r'^\[CURRENT_FRAME\] (-?\d+)$', text, re.M)]
                    if frames and max(frames) >= args.last_frame:
                        break
                    if proc.poll() is not None:
                        break
                    time.sleep(0.25)
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
    except OSError as exc:
        p.exit(1, f'cannot run Playback Dolphin: {exc}\n')
    passed = bool(frames and frames[0] == -123 and max(frames) >= args.last_frame
                  and all(b == a+1 for a,b in zip(frames, frames[1:])))
    result = {'command': command, 'replay': str(args.replay.resolve()),
        'firstReportedFrame': min(frames) if frames else None,
        'lastReportedFrame': max(frames) if frames else None,
        'requestedLastFrame': args.last_frame, 'frameProgressionPassed': passed,
        'shouldResync': False, 'stateEqualityMeasured': False,
        'note': 'Process stopped by harness after frame reports; exit is not a game-end assertion.'}
    (out / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
