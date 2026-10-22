"""Record real native events across checkpoint branches; requires the user's ISO.

Run in the GCC 14 container from /work. Outputs are unfinished match recordings,
not fabricated complete games. Parser/playback validation are separate steps.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from yt2slp.backend import NativeLinuxBackend, RunConfig
from yt2slp.match import MatchConfig, NEUTRAL_PADS, PadInput, PlayerConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', type=Path, default=os.environ.get('YT2SLP_ISO', '/assets/melee.iso'))
    args = parser.parse_args()
    with NativeLinuxBackend() as backend:
        backend.initialize(RunConfig(
            Path('build/headless/melee_headless'), Path('build/game/melee_game.so'),
            args.iso, Path('.local/runs'),
            match=MatchConfig(31, (PlayerConfig(2), PlayerConfig(20))),
        ))
        backend.start(Path('third_party/melee-unlocked/port/scripts/native_vs.txt'), timeout=180)
        for _ in range(240):
            backend.step(NEUTRAL_PADS)
        captured = backend.observe()
        checkpoint = backend.capture()
        directory = backend.last_run_dir
        chosen = (PadInput(stick_x=80), *NEUTRAL_PADS[1:])
        branches = [('original', chosen), ('identical', chosen),
                    ('divergent', NEUTRAL_PADS), ('selected', chosen)]
        traces = {}
        for index, (name, pads) in enumerate(branches):
            if index:
                backend.restore(checkpoint)
                if backend.observe() != captured:
                    raise RuntimeError('unstable restored state')
            traces[name] = tuple(backend.step(pads) for _ in range(180))
            before = backend.observe()
            backend.record(directory / (name + '.slp'))
            if backend.observe() != before:
                raise RuntimeError('record advanced the paused session')
        files = {name: (directory / (name + '.slp')).read_bytes() for name, _ in branches}
        if not files['original'] == files['identical'] == files['selected']:
            raise RuntimeError('identical continuations produced different replay bytes')
        if files['original'] == files['divergent']:
            raise RuntimeError('different inputs did not change replay bytes')
        if not traces['original'] == traces['identical'] == traces['selected']:
            raise RuntimeError('identical continuations produced different selected states')
        if traces['original'] == traces['divergent']:
            raise RuntimeError('different inputs did not change selected states')
        report = {
            'directory': str(directory), 'bytes': len(files['selected']),
            'captured_match_frame': captured.match_frame,
            'final_match_frame': backend.observe().match_frame,
            'identical_restored_bytes': True, 'different_branch_bytes': True,
            'identical_restored_selected_states': True,
            'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
            'game_end_fabricated': False, 'parser_validated': False, 'playback_validated': False,
        }
        (directory / 'recording-result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
