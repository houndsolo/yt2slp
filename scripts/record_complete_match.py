"""ISO-backed complete-match recording and restoration check; run in Docker.

Uses the game's default timed rules and ordinary controller input. Neither the
native game nor the replay is patched to force a result. Parser and official
Playback validation remain separate, independently reported checks.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from yt2slp.backend import NativeLinuxBackend, RunConfig
from yt2slp.match import MatchConfig, NEUTRAL_PADS, PadInput, PlayerConfig


def finish(backend, pads, limit):
    for _ in range(limit):
        backend.step(pads)
        status = backend.recording_status()
        if status.ended:
            return status
    backend.record(backend.last_run_dir / 'incomplete.slp')
    raise RuntimeError(f'no game-generated Game End within {limit} steps; retained incomplete replay')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', type=Path, default=os.environ.get('YT2SLP_ISO', '/assets/melee.iso'))
    parser.add_argument('--stage', type=int, choices=(31, 32), default=31)
    parser.add_argument('--capture-after', type=int, default=6900)
    parser.add_argument('--continuation-limit', type=int, default=3000)
    args = parser.parse_args()
    if args.capture_after < 1 or args.continuation_limit < 1:
        parser.error('capture-after and continuation-limit must be positive')
    with NativeLinuxBackend() as backend:
        backend.initialize(RunConfig(
            Path('build/headless/melee_headless'), Path('build/game/melee_game.so'),
            args.iso, Path('.local/runs'),
            match=MatchConfig(args.stage, (PlayerConfig(2), PlayerConfig(20))),
        ))
        backend.start(Path('third_party/melee-unlocked/port/scripts/native_vs.txt'), timeout=180)
        directory = backend.last_run_dir
        print(f'Artifacts: {directory}', flush=True)
        right = (PadInput(stick_x=80), *NEUTRAL_PADS[1:])
        left = (PadInput(stick_x=-80), *NEUTRAL_PADS[1:])
        for _ in range(args.capture_after):
            backend.step(right)
        captured = backend.observe()
        initial_status = backend.recording_status()
        if initial_status.ended:
            raise RuntimeError('match already ended before checkpoint; choose an earlier capture')
        checkpoint = backend.capture()
        results = {}
        for index, (name, pads) in enumerate((('original', right), ('identical', right),
                                            ('divergent', left), ('selected', right))):
            if index:
                backend.restore(checkpoint)
                if backend.observe() != captured or backend.recording_status() != initial_status:
                    raise RuntimeError('restore failed to recover pre-ending state and recording status')
            end = finish(backend, pads, args.continuation_limit)
            state = backend.observe()
            output = directory / (name + '.slp')
            backend.record(output)
            if backend.observe() != state or backend.recording_status() != end:
                raise RuntimeError('record changed the paused state or recording status')
            data = output.read_bytes()
            results[name] = {'path': str(output), 'last_frame': end.last_frame,
                             'ended': end.ended, 'bytes': len(data),
                             'sha256': hashlib.sha256(data).hexdigest()}
            # Post-ending callbacks must be safe and cannot append to the replay.
            for _ in range(6):
                backend.step(NEUTRAL_PADS)
            settled = directory / (name + '-settled.slp')
            backend.record(settled)
            if settled.read_bytes() != data or backend.recording_status() != end:
                raise RuntimeError('recording changed after game-generated ending')
        hashes = {name: value['sha256'] for name, value in results.items()}
        if not hashes['original'] == hashes['identical'] == hashes['selected']:
            raise RuntimeError('restored identical endings produced different replay bytes')
        if hashes['original'] == hashes['divergent']:
            raise RuntimeError('divergent branch did not change replay bytes')
        report = {'directory': str(directory), 'captured_match_frame': captured.match_frame,
                  'stage': args.stage, 'branches': results, 'restores': 3,
                  'restored_pre_ending_status': True, 'post_ending_stream_stable': True,
                  'identical_restored_bytes': True, 'different_branch_bytes': True,
                  'game_end_fabricated': False, 'parser_validated': False,
                  'playback_validated': False, 'state_equality_measured': False}
        (directory / 'complete-result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
