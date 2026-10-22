#!/usr/bin/env python3
"""Exercise official Slippi Playback with a private profile; retain stdout evidence.

Run on the host (optionally under xvfb-run). Frame reports establish playback
progression, not equality of rendered or simulated state with the native engine.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time


def verify_complete_report(report, replay_sha256, last_frame):
    """Bind independent completion evidence to the exact replay being launched."""
    if (not isinstance(report, dict) or report.get('completeMatchValidated') is not True
            or report.get('replaySha256') != replay_sha256
            or report.get('lastFrame') != last_frame
            or not isinstance(report.get('metadata'), dict)
            or report['metadata'].get('lastFrame') != last_frame
            or not isinstance(report.get('gameEnd'), dict)
            or report['gameEnd'].get('gameEndMethod') not in (1, 2, 3, 7)):
        raise ValueError('complete parser report does not match this replay and final frame')
    return report['gameEnd']


def assess_reports(text, last_frame, replay_path, require_complete=False):
    frames = [int(n) for n in re.findall(r'^\[CURRENT_FRAME\] (-?\d+)$', text, re.M)]
    end_frames = [int(n) for n in re.findall(r'^\[GAME_END_FRAME\] (-?\d+)$', text, re.M)]
    paths = re.findall(r'^\[FILE_PATH\] (.+)$', text, re.M)
    progression = bool(frames and frames[0] == -123 and max(frames) >= last_frame
                       and all(b == a+1 for a, b in zip(frames, frames[1:])))
    end_match = bool(end_frames and all(n == last_frame for n in end_frames))
    file_match = bool(paths and all(p == str(replay_path) for p in paths))
    return {'firstReportedFrame': min(frames) if frames else None,
            'lastReportedFrame': max(frames) if frames else None,
            'officialReportedGameEndFrame': end_frames[-1] if end_frames else None,
            'replayPathMatched': file_match, 'gameEndFrameMatched': end_match,
            'frameProgressionPassed': progression,
            'playbackPassed': progression and file_match and (end_match or not require_complete)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dolphin', type=Path, default=os.environ.get('YT2SLP_DOLPHIN'))
    p.add_argument('--iso', type=Path, default=os.environ.get('YT2SLP_ISO'))
    p.add_argument('--replay', type=Path, required=True)
    p.add_argument('--last-frame', type=int, required=True)
    p.add_argument('--parser-report', type=Path, help='Require independent complete-match evidence for this exact replay')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout', type=float, default=180)
    args = p.parse_args()
    if args.last_frame < 0 or not math.isfinite(args.timeout) or args.timeout <= 0:
        p.error("last frame must be nonnegative and timeout finite and positive")
    for value in (args.dolphin, args.iso, args.replay):
        if value is None or not value.is_file():
            p.error(f'missing input: {value}')
    replay_path = args.replay.resolve()
    replay_sha256 = hashlib.sha256(replay_path.read_bytes()).hexdigest()
    parser_end = None
    if args.parser_report is not None:
        try:
            parser_end = verify_complete_report(json.loads(args.parser_report.read_text()),
                                                replay_sha256, args.last_frame)
        except (OSError, ValueError, AttributeError, TypeError) as exc:
            p.error(str(exc))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    user = out / 'user'
    (user / 'Config').mkdir(parents=True)
    (user / 'Config/Dolphin.ini').write_text(
        '[Core]\nCPUThread = False\nDSPHLE = True\nGFXBackend = OGL\n'
        '[Interface]\nConfirmStop = False\n[DSP]\nBackend = No audio output\n')
    request = out / 'request.json'
    request_data = {'mode': 'normal', 'replay': str(replay_path),
                    'commandId': 'yt2slp-validation', 'startFrame': -123, 'shouldResync': False}
    if parser_end is None:
        request_data['endFrame'] = args.last_frame
    # For a complete match, let official Playback follow the recording's ending.
    request.write_text(json.dumps(request_data, indent=2)+'\n')
    command = [str(args.dolphin.resolve()), '--exec='+str(args.iso.resolve()),
        '--slippi-input='+str(request), '--user='+str(user), '--batch', '--cout']
    text = ""
    reached_at = None
    try:
        with (out / 'stdout.log').open('wb') as log:
            proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            try:
                deadline = time.monotonic() + args.timeout
                while time.monotonic() < deadline:
                    text = (out / 'stdout.log').read_text(errors='replace')
                    assessment = assess_reports(text, args.last_frame, replay_path, parser_end is not None)
                    if assessment['playbackPassed']:
                        if reached_at is None:
                            reached_at = time.monotonic()
                        if parser_end is None or time.monotonic() - reached_at >= 2:
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
    text = (out / 'stdout.log').read_text(errors='replace')
    assessment = assess_reports(text, args.last_frame, replay_path, parser_end is not None)
    result = {'command': command, 'replay': str(replay_path), 'replaySha256': replay_sha256,
        'requestedLastFrame': args.last_frame, **assessment,
        'parserGameEnd': parser_end, 'independentCompleteMatchValidated': parser_end is not None,
        'shouldResync': False, 'stateEqualityMeasured': False,
        'endingOutcomeComparedWithDolphin': False,
        'note': 'Game End method/placements come from independent parsing; Dolphin frame reports do not prove result-state equality.'}
    (out / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if result['playbackPassed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
